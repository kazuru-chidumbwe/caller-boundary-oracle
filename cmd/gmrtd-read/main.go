// Command gmrtd-read runs one oracle observation against gmrtd: a synthetic chip from a
// profile, one shipped ReadDocument call, and the caller-boundary outcome for the
// mechanism the profile targets. Build with -tags gmrtd_8fea245 and
// -modfile gomod/gmrtd-8fea245.mod to measure the earlier gmrtd pin.
package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/gmrtd/gmrtd/password"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/classifier"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/guard"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/gmrtdcompat"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/gmrtdrun"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/output"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/profile"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/provenance"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/runid"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/simulator"
)

type runArtifact struct {
	output.Meta
	Outcome       classifier.Outcome `json:"outcome"`
	Score         *int               `json:"observability_score"`
	Meaning       string             `json:"observability_meaning"`
	CallerOptions callerOptions      `json:"caller_options"`
	FaultPoint    string             `json:"fault_point"`
	gmrtdrun.Result
}

type callerOptions struct {
	AllowBacFallback bool `json:"allow_bac_fallback"`
	Guard            bool `json:"guard"`
}

func main() {
	profilePath := flag.String("profile", "", "synthetic chip profile JSON")
	logDir := flag.String("log-dir", "logs", "output directory for run artifacts")
	variant := flag.String("variant", "baseline", "run variant label")
	allowFallback := flag.Bool("allow-bac-fallback", false, "call AllowBacFallbackOnPaceError (gmrtd v1.1.3+)")
	useGuard := flag.Bool("guard", false, "apply guard.Require after ReadDocument")
	suiteID := flag.String("suite-id", "", "suite id (metadata)")
	suiteSeed := flag.Int("suite-seed", 1, "suite seed (metadata)")
	suiteN := flag.Int("suite-n", 1, "runs per suite entry (metadata)")
	runIndex := flag.Int("run-index", 1, "1-based run index within the suite entry")
	figureID := flag.String("figure-id", "", "suite cell identifier")
	flag.Parse()
	if *profilePath == "" {
		fatal("flags", fmt.Errorf("-profile is required"))
	}

	p, err := profile.Load(*profilePath)
	if err != nil {
		fatal("profile", err)
	}
	mechanism := guard.Mechanism(strings.ToUpper(p.Mechanism))
	switch mechanism {
	case guard.PACE, guard.CA, guard.AA:
	default:
		fatal("profile", fmt.Errorf("unsupported mechanism %q", p.Mechanism))
	}
	pass, err := password.NewPasswordMrzi(p.MRZ.DocumentNumber, p.MRZ.DateOfBirth, p.MRZ.DateOfExpiry)
	if err != nil {
		fatal("password", err)
	}
	chip, closeChip, err := openChip(p, *profilePath, pass)
	if err != nil {
		fatal("chip", err)
	}
	opts := gmrtdrun.Options{AllowBacFallback: *allowFallback, Guard: *useGuard}
	res, err := gmrtdrun.Run(mechanism, chip, pass, opts)
	closeChip()
	if err != nil {
		fatal("run", err)
	}
	outcome := classifier.Classify(res.Observation)

	var optNames []string
	if opts.AllowBacFallback {
		optNames = append(optNames, "allow-bac-fallback")
	}
	if opts.Guard {
		optNames = append(optNames, "guard")
	}
	prov, err := provenance.Collect(provenance.Options{
		ProfilePath:   *profilePath,
		SuiteID:       *suiteID,
		SuiteSeed:     *suiteSeed,
		SuiteN:        *suiteN,
		RunIndex:      *runIndex,
		Driver:        "go/gmrtd-read",
		Variant:       *variant,
		CallerOptions: strings.Join(optNames, ","),
		GmrtdCommit:   gmrtdcompat.Commit,
	})
	if err != nil {
		fatal("provenance", err)
	}

	runID := runid.New(fmt.Sprintf("%s-gmrtd-%s-%s", p.ID, gmrtdcompat.Commit[:7], *variant))
	artifact := runArtifact{
		Meta: output.Meta{
			RunID:      runID,
			TestCase:   p.ID,
			Library:    "gmrtd",
			Mechanism:  string(mechanism),
			Condition:  p.Condition,
			Tier:       p.Tier,
			Variant:    *variant,
			FigureID:   *figureID,
			Provenance: prov,
		},
		Outcome:       outcome,
		Score:         outcome.ScorePtr(),
		Meaning:       outcome.Meaning(),
		CallerOptions: callerOptions{AllowBacFallback: opts.AllowBacFallback, Guard: opts.Guard},
		FaultPoint:    faultPoint(p, mechanism),
		Result:        res,
	}
	if err := output.WriteJSON(*logDir, runID, artifact); err != nil {
		fatal("write", err)
	}
	fmt.Printf("%s %s gmrtd %s: %s\n", p.ID, *variant, gmrtdcompat.Commit[:7], outcome)
}

// faultPoint names the step the profile injects the failure into ("" when nothing is injected).
func faultPoint(p *profile.Profile, m guard.Mechanism) string {
	switch m {
	case guard.PACE:
		if p.Peer == "vsmartcard" {
			return profile.VsmartcardPaceFaultPoint(p.Vsmartcard.PaceStep)
		}
		if p.CardAccessHex == "" || p.Injection.PaceFailOn == "" {
			return ""
		}
		return "PACE/" + p.Injection.PaceFailOn
	case guard.CA:
		return "CA/" + p.CAInjection.CaFailOn
	case guard.AA:
		if p.Peer == "vsmartcard" {
			if p.Vsmartcard.AaSW == "" {
				return ""
			}
			return "AA/internal_authenticate"
		}
		return "AA/" + p.AAInjection.AaFailOn
	}
	return ""
}

// openChip returns the peer the profile asks for and a function that releases it.
func openChip(p *profile.Profile, profilePath string, pass *password.Password) (gmrtdrun.Chip, func(), error) {
	switch p.Peer {
	case "":
		cfg, err := simulator.ChipConfigFromProfile(p)
		if err != nil {
			return nil, nil, err
		}
		return simulator.NewDocumentChip(cfg, pass), func() {}, nil
	case "vsmartcard":
		root, err := os.Getwd()
		if err != nil {
			return nil, nil, err
		}
		peer, err := simulator.StartVsmartcard(root, simulator.VsmartcardConfig{ProfilePath: profilePath})
		if err != nil {
			return nil, nil, err
		}
		return peer, peer.Close, nil
	}
	return nil, nil, fmt.Errorf("unknown peer %q", p.Peer)
}

func fatal(step string, err error) {
	fmt.Fprintf(os.Stderr, "%s: %v\n", step, err)
	os.Exit(2)
}
