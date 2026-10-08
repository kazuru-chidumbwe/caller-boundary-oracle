// @simplewebauthn/server driver: verify one fault-peer case as an integrator would; print the raw record.
// Same contract as webauthn/drivers/py_webauthn_driver.py. Usage: node simplewebauthn_driver.js <case-dir>
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const swa = require('@simplewebauthn/server');
const version = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'node_modules', '@simplewebauthn', 'server', 'package.json'), 'utf8')).version;

const b64d = (s) => Buffer.from(s, 'base64url');

async function main() {
  const dir = process.argv[2];
  const opts = JSON.parse(fs.readFileSync(path.join(dir, 'options.json'), 'utf8'));
  const body = fs.readFileSync(path.join(dir, 'response.json'));
  const rec = {
    library: 'simplewebauthn', version,
    passed_sha256: crypto.createHash('sha256').update(body).digest('hex'),
    returned_error: false, error_type: null, error: null, fields: {},
  };
  const response = JSON.parse(body.toString('utf8'));
  try {
    if (!opts.credential) {
      const r = await swa.verifyRegistrationResponse({
        response, expectedChallenge: opts.challenge, expectedOrigin: opts.origin,
        expectedRPID: opts.rpId, requireUserVerification: opts.requireUserVerification,
        supportedAlgorithmIDs: opts.pubKeyCredParams || [-7],
      });
      const i = r.registrationInfo || {};
      rec.fields = { verified: r.verified, userVerified: i.userVerified ?? null,
        credentialBackedUp: i.credentialBackedUp ?? null, credentialDeviceType: i.credentialDeviceType ?? null,
        fmt: i.fmt ?? null };
    } else {
      const c = opts.credential;
      const r = await swa.verifyAuthenticationResponse({
        response, expectedChallenge: opts.challenge, expectedOrigin: opts.origin,
        expectedRPID: opts.rpId, requireUserVerification: opts.requireUserVerification,
        credential: { id: c.id, publicKey: new Uint8Array(b64d(c.publicKeyCose)), counter: c.signCount },
      });
      const i = r.authenticationInfo || {};
      rec.fields = { verified: r.verified, userVerified: i.userVerified ?? null,
        credentialBackedUp: i.credentialBackedUp ?? null, credentialDeviceType: i.credentialDeviceType ?? null,
        newCounter: i.newCounter ?? null };
    }
  } catch (e) {
    rec.returned_error = true;
    rec.error_type = (e && e.name) || 'Error';
    rec.error = String((e && e.message) || e).slice(0, 300);
  }
  console.log(JSON.stringify(rec));
}

main();
