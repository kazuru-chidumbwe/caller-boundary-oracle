// go-webauthn driver: verify one fault-peer case as an integrator would and print the raw record.
// Same contract as webauthn/drivers/py_webauthn_driver.py. Usage: gowebauthn-driver <case-dir>
package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"

	"github.com/go-webauthn/webauthn/protocol"
	"github.com/go-webauthn/webauthn/webauthn"
)

type options struct {
	RPID       string `json:"rpId"`
	RPName     string `json:"rpName"`
	Origin     string `json:"origin"`
	Challenge  string `json:"challenge"`
	UserID     string `json:"userId"`
	UserName   string `json:"userName"`
	RequireUV  bool   `json:"requireUserVerification"`
	Credential *struct {
		ID        string `json:"id"`
		COSE      string `json:"publicKeyCose"`
		SignCount uint32 `json:"signCount"`
	} `json:"credential"`
}

type user struct {
	id    []byte
	name  string
	creds []webauthn.Credential
}

func (u *user) WebAuthnID() []byte                         { return u.id }
func (u *user) WebAuthnName() string                       { return u.name }
func (u *user) WebAuthnDisplayName() string                { return u.name }
func (u *user) WebAuthnCredentials() []webauthn.Credential { return u.creds }

func b64d(s string) []byte {
	b, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		panic(err)
	}
	return b
}

func version() string {
	if bi, ok := debug.ReadBuildInfo(); ok {
		for _, d := range bi.Deps {
			if d.Path == "github.com/go-webauthn/webauthn" {
				return d.Version
			}
		}
	}
	return "unknown"
}

func main() {
	dir := os.Args[1]
	raw, _ := os.ReadFile(filepath.Join(dir, "options.json"))
	var o options
	if err := json.Unmarshal(raw, &o); err != nil {
		panic(err)
	}
	body, _ := os.ReadFile(filepath.Join(dir, "response.json"))
	sum := sha256.Sum256(body)
	rec := map[string]any{"library": "go-webauthn", "version": version(), "passed_sha256": hex.EncodeToString(sum[:]),
		"returned_error": false, "error_type": nil, "error": nil, "fields": map[string]any{}}
	w, err := webauthn.New(&webauthn.Config{RPID: o.RPID, RPDisplayName: o.RPName, RPOrigins: []string{o.Origin}})
	if err != nil {
		panic(err)
	}
	uv := protocol.VerificationPreferred
	if o.RequireUV {
		uv = protocol.VerificationRequired
	}
	u := &user{id: b64d(o.UserID), name: o.UserName}
	fail := func(err error) {
		rec["returned_error"] = true
		rec["error_type"] = fmt.Sprintf("%T", err)
		msg := err.Error()
		if e, ok := err.(*protocol.Error); ok {
			msg = e.Details + ": " + e.DevInfo
		}
		if len(msg) > 300 {
			msg = msg[:300]
		}
		rec["error"] = strings.ReplaceAll(msg, "\n", " ")
	}
	if o.Credential == nil {
		session := webauthn.SessionData{Challenge: o.Challenge, RelyingPartyID: o.RPID, UserID: u.id, UserVerification: uv,
			CredParams: []protocol.CredentialParameter{{Type: protocol.PublicKeyCredentialType, Algorithm: -7}}}
		parsed, err := protocol.ParseCredentialCreationResponseBytes(body)
		if err == nil {
			var c *webauthn.Credential
			if c, err = w.CreateCredential(u, session, parsed); err == nil {
				rec["fields"] = map[string]any{"user_verified": c.Flags.UserVerified, "backup_eligible": c.Flags.BackupEligible,
					"backup_state": c.Flags.BackupState, "attestation_type": c.AttestationType, "attestation_format": c.AttestationFormat}
			}
		}
		if err != nil {
			fail(err)
		}
	} else {
		id := b64d(o.Credential.ID)
		u.creds = []webauthn.Credential{{ID: id, PublicKey: b64d(o.Credential.COSE), AttestationType: "none",
			Flags:         webauthn.CredentialFlags{UserPresent: true, UserVerified: true},
			Authenticator: webauthn.Authenticator{AAGUID: make([]byte, 16), SignCount: o.Credential.SignCount}}}
		session := webauthn.SessionData{Challenge: o.Challenge, RelyingPartyID: o.RPID, UserID: u.id, UserVerification: uv,
			AllowedCredentialIDs: [][]byte{id}}
		parsed, err := protocol.ParseCredentialRequestResponseBytes(body)
		if err == nil {
			var c *webauthn.Credential
			if c, err = w.ValidateLogin(u, session, parsed); err == nil {
				rec["fields"] = map[string]any{"user_verified": c.Flags.UserVerified, "backup_state": c.Flags.BackupState,
					"clone_warning": c.Authenticator.CloneWarning, "sign_count": c.Authenticator.SignCount}
			}
		}
		if err != nil {
			fail(err)
		}
	}
	out, _ := json.Marshal(rec)
	fmt.Println(string(out))
}
