package simulator

import (
	"fmt"

	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/profile"
)

// ChipConfigFromProfile builds the harness chip described by a profile.
func ChipConfigFromProfile(p *profile.Profile) (ChipConfig, error) {
	cfg := ChipConfig{
		CardAccessHex: p.CardAccessHex,
		PaceSW:        p.Injection.PaceSW,
		PaceFailOn:    p.Injection.PaceFailOn,
		PaceChannel:   p.Injection.PaceChannel,
		CaSW:          p.CAInjection.CaSW,
		AaSW:          p.AAInjection.AaSW,
	}
	if p.Dg14HexPath != "" {
		b, err := profile.LoadHexFile(p.Dg14HexPath)
		if err != nil {
			return cfg, fmt.Errorf("dg14: %w", err)
		}
		cfg.Dg14Hex = fmt.Sprintf("%X", b)
	}
	if p.Dg15HexPath != "" {
		b, err := profile.LoadHexFile(p.Dg15HexPath)
		if err != nil {
			return cfg, fmt.Errorf("dg15: %w", err)
		}
		cfg.Dg15Hex = fmt.Sprintf("%X", b)
	}
	cfg.Dual = p.Dual
	if cfg.Dg14Hex != "" && cfg.Dg15Hex != "" {
		return cfg, fmt.Errorf("profile sets both DG14 and DG15; target one mechanism per profile")
	}
	return cfg, nil
}
