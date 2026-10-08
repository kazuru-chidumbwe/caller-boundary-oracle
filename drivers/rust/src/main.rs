// One oracle observation against passauf: start a chip (harness chip-serve or the independent vsmartcard
// chip), call passauf::session::read_document the way an application does, and record the caller-boundary
// outcome. passauf falls back to BAC on any PACE error and logs the error; the returned DocumentRead names
// the authentication used, which is the only record of the fallback the caller receives.
use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use passauf::session::{read_document, AccessKey, Authentication, ReadOptions};
use passauf::smartcard_abstractions::{CallbackSmartcard, Smartcard};
use serde_json::{json, Value};

// ---------------------------------------------------------------- oracle

struct Observation {
    fired: bool,
    failed: bool,
    succeeded: bool,
    returned_error: bool,
    status_signal: bool,
}

/// Same predicate as classifier/observability.go, .py, Observability.java, Oracle.cs and dmrtd_read.dart.
fn classify(o: &Observation) -> &'static str {
    if o.failed && o.succeeded {
        return "invalid";
    }
    if !o.fired {
        return "not_applicable";
    }
    if o.returned_error {
        return "surfaced";
    }
    if o.status_signal {
        return "status_only";
    }
    "silent"
}

fn score(outcome: &str) -> Value {
    match outcome {
        "silent" => json!(0),
        "status_only" => json!(1),
        "surfaced" => json!(2),
        _ => Value::Null,
    }
}

fn meaning(outcome: &str) -> &'static str {
    match outcome {
        "silent" => "silent: call succeeded, failure not reachable by the caller",
        "status_only" => "status-only: call succeeded, failure recorded in a returned status field",
        "surfaced" => "surfaced: error returned or thrown to the caller",
        "not_applicable" => "not applicable: injected failure did not fire",
        _ => "invalid: library reported the step as both failed and successful",
    }
}

// ---------------------------------------------------------------- transport

/// Acts as the reader for a chip process speaking the vpcd socket protocol. Mirrors
/// simulator/vpcd_peer.go, VsmartcardCardService.java, VpcdTransport.cs and the dmrtd driver.
struct Vpcd {
    sock: TcpStream,
    chip: Child,
    trace: Arc<Mutex<Vec<Value>>>,
}

impl Vpcd {
    fn start(exe: &str, args_for_port: &dyn Fn(u16) -> Vec<String>) -> std::io::Result<Vpcd> {
        let listener = TcpListener::bind("127.0.0.1:0")?;
        let port = listener.local_addr()?.port();
        let chip = Command::new(exe).args(args_for_port(port)).stdin(Stdio::null()).spawn()?;
        listener.set_nonblocking(true)?;
        let deadline = Instant::now() + Duration::from_secs(30);
        let sock = loop {
            match listener.accept() {
                Ok((s, _)) => break s,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock && Instant::now() < deadline => {
                    std::thread::sleep(Duration::from_millis(20))
                }
                Err(e) => return Err(e),
            }
        };
        sock.set_nonblocking(false)?;
        sock.set_read_timeout(Some(Duration::from_secs(30)))?;
        let mut v = Vpcd { sock, chip, trace: Arc::new(Mutex::new(vec![])) };
        v.send(&[0x01])?; // power on
        v.send(&[0x04])?; // get ATR
        v.receive()?;
        Ok(v)
    }

    fn send(&mut self, msg: &[u8]) -> std::io::Result<()> {
        let len = (msg.len() as u16).to_be_bytes();
        self.sock.write_all(&len)?;
        self.sock.write_all(msg)
    }

    fn receive(&mut self) -> std::io::Result<Vec<u8>> {
        let mut hdr = [0u8; 2];
        self.sock.read_exact(&mut hdr)?;
        let mut msg = vec![0u8; u16::from_be_bytes(hdr) as usize];
        self.sock.read_exact(&mut msg)?;
        Ok(msg)
    }

    fn transceive(&mut self, capdu: &[u8]) -> Option<Vec<u8>> {
        self.send(capdu).ok()?;
        let rsp = self.receive().ok()?;
        let ok = rsp.len() >= 2 && rsp[rsp.len() - 2] == 0x90 && rsp[rsp.len() - 1] == 0x00;
        let ins = capdu.get(1).copied().unwrap_or(0);
        self.trace.lock().unwrap().push(json!({
            "label": format!("INS {:02X}", ins), "capdu": hex(capdu), "rapdu": hex(&rsp), "success": ok
        }));
        Some(rsp)
    }

    fn close(mut self) {
        let _ = self.send(&[0x00]); // power off
        let _ = self.sock.shutdown(std::net::Shutdown::Both);
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            if let Ok(Some(_)) = self.chip.try_wait() {
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        let _ = self.chip.kill();
        let _ = self.chip.wait();
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{:02X}", x)).collect()
}

/// passauf logs through simplelog; this keeps the lines so the driver can read the library's own record.
#[derive(Clone)]
struct LogBuf(Arc<Mutex<Vec<u8>>>);

impl Write for LogBuf {
    fn write(&mut self, b: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(b);
        Ok(b.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

// ---------------------------------------------------------------- driver

fn main() {
    std::process::exit(run());
}

fn parse(argv: &[String]) -> HashMap<String, String> {
    let mut out = HashMap::new();
    let mut i = 0;
    while i + 1 < argv.len() {
        out.insert(argv[i].clone(), argv[i + 1].clone());
        i += 2;
    }
    out
}

fn run() -> i32 {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let a = parse(&argv);
    if let Some(p) = a.get("-check-vectors") {
        return check_vectors(p);
    }
    let root = std::env::current_dir().unwrap().to_string_lossy().to_string();
    let profile_path = a.get("-profile").expect("-profile").clone();
    let profile: Value = serde_json::from_str(&fs::read_to_string(&profile_path).unwrap()).unwrap();
    let id = profile["id"].as_str().unwrap_or("").to_string();
    let mechanism = profile["mechanism"].as_str().unwrap_or("").to_uppercase();
    let mrz = &profile["mrz"];
    let vsc = profile["peer"].as_str() == Some("vsmartcard");
    let variant = a.get("-variant").cloned().unwrap_or_else(|| "default".into());
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let report = format!("{}/chip-report-{}-{}.json", std::env::temp_dir().display(), nanos, std::process::id());

    let logbuf = LogBuf(Arc::new(Mutex::new(vec![])));
    let _ = simplelog::WriteLogger::init(simplelog::LevelFilter::Trace, simplelog::Config::default(), logbuf.clone());

    let (exe, args_for_port): (String, Box<dyn Fn(u16) -> Vec<String>>) = if vsc {
        let (pp, rp, root2) = (profile_path.clone(), report.clone(), root.clone());
        ("python3".into(), Box::new(move |p| vec![format!("{}/tools/vsmartcard/emrtd_card.py", root2), "--port".into(),
            p.to_string(), "--profile".into(), pp.clone(), "--report".into(), rp.clone()]))
    } else {
        let (pp, rp) = (profile_path.clone(), report.clone());
        (a.get("-chip-serve").cloned().unwrap_or_else(|| "bin/chip-serve".into()),
         Box::new(move |p| vec!["-profile".into(), pp.clone(), "-port".into(), p.to_string(), "-report".into(), rp.clone()]))
    };

    let mut authentication: Option<Authentication> = None;
    let mut read_err = String::new();
    let mut trace = vec![];
    match Vpcd::start(&exe, &*args_for_port) {
        Err(e) => read_err = format!("transport: {}", e),
        Ok(vpcd) => {
            let tr = vpcd.trace.clone();
            let cell = Arc::new(Mutex::new(Some(vpcd)));
            let c2 = cell.clone();
            {
                let card = CallbackSmartcard::new(move |capdu: &[u8]| c2.lock().unwrap_or_else(|e| e.into_inner()).as_mut()?.transceive(capdu));
                let mut boxed: Box<dyn Smartcard> = Box::new(card);
                let options = ReadOptions {
                    access_key: AccessKey::Mrz {
                        document_number: mrz["document_number"].as_str().unwrap_or("").into(),
                        date_of_birth: mrz["date_of_birth"].as_str().unwrap_or("").into(),
                        date_of_expiry: mrz["date_of_expiry"].as_str().unwrap_or("").into(),
                    },
                    read_binary_files: false,
                    dump_path: None,
                    file_prefix: "document".into(),
                    print: false,
                };
                // passauf panics when a response is missing or too short (iso7816.rs, exchange: "The card
                // stopped responding mid-exchange"). Its own app integration (src/ffi/mod.rs) wraps
                // read_document in catch_unwind and hands the panic to the app as an error; the driver
                // calls it the same way, so a panic reaches the caller as an error.
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    read_document(&mut boxed, &options, &mut |_| {})
                }));
                match outcome {
                    Ok(Ok(doc)) => authentication = doc.authentication,
                    Ok(Err(e)) => read_err = format!("SessionError::{}: {}", e.kind(), e),
                    Err(payload) => {
                        let msg = payload.downcast_ref::<&str>().map(|s| s.to_string())
                            .or_else(|| payload.downcast_ref::<String>().cloned())
                            .unwrap_or_else(|| "non-string panic payload".into());
                        read_err = format!("panic: {}", msg);
                    }
                }
            }
            if let Some(v) = cell.lock().unwrap_or_else(|e| e.into_inner()).take() {
                v.close();
            }
            trace = tr.lock().unwrap_or_else(|e| e.into_inner()).clone();
        }
    }

    let mut fired = false;
    if let Ok(s) = fs::read_to_string(&report) {
        if let Ok(r) = serde_json::from_str::<Value>(&s) {
            fired = r["fault_delivered"][mechanism.as_str()].as_bool() == Some(true);
        }
        let _ = fs::remove_file(&report);
    }

    let log_text = String::from_utf8_lossy(&logbuf.0.lock().unwrap()).to_string();
    let library_log: Vec<String> = log_text.lines().map(|l| l.to_string()).collect();
    let used_pace = matches!(authentication, Some(Authentication::Pace { .. }));
    // passauf records a failed PACE attempt only in its log (warn! of the error, then "Falling back to BAC.")
    // and in DocumentRead.authentication, which names BAC: the status field a caller can check.
    let pace_failed_logged = library_log.iter().any(|l| l.contains("Falling back to BAC"));
    let (failed, succeeded, status_signal) = if mechanism == "PACE" {
        (pace_failed_logged, used_pace, authentication.is_some() && !used_pace)
    } else {
        (false, false, false)
    };
    let obs = Observation { fired, failed, succeeded, returned_error: !read_err.is_empty(), status_signal };
    let outcome = classify(&obs);
    let run_index: u64 = a.get("-run-index").and_then(|s| s.parse().ok()).unwrap_or(1);
    let micros = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_micros();
    let run_id = format!("{}-passauf-{}-{}-{:06}", id, variant, micros, run_index);
    let result = json!({
        "run_id": run_id,
        "test_case": id,
        "library": "passauf",
        "mechanism": mechanism,
        "condition": profile["condition"],
        "tier": profile.get("tier").cloned().unwrap_or(json!("wire")),
        "variant": variant,
        "provenance": provenance(&root, &profile_path, &a, &variant),
        "outcome": outcome,
        "observability_score": score(outcome),
        "observability_meaning": meaning(outcome),
        "observation": {
            "fired": obs.fired, "failed": obs.failed, "succeeded": obs.succeeded,
            "returned_error": obs.returned_error, "status_signal": obs.status_signal,
        },
        "fault_point": fault_point(&profile, &mechanism, vsc),
        "access_control": authentication.as_ref().map(|x| x.to_string()).unwrap_or_default(),
        "read_err": read_err,
        "library_log": library_log,
        "trace": trace,
    });
    let log_dir = a.get("-log-dir").cloned().unwrap_or_else(|| "logs".into());
    fs::create_dir_all(&log_dir).unwrap();
    fs::write(format!("{}/{}.json", log_dir, run_id), serde_json::to_string_pretty(&result).unwrap() + "\n").unwrap();
    println!("{} {} passauf: {}", id, variant, outcome);
    0
}

fn fault_point(p: &Value, mechanism: &str, vsc: bool) -> String {
    if mechanism == "PACE" {
        if vsc {
            let step = p["vsmartcard"]["pace_step"].as_str().unwrap_or("");
            if step.is_empty() {
                return String::new();
            }
            if step == "mse" {
                return "PACE/mse_set_at".into();
            }
            if step.len() == 3 && step.starts_with("ga") {
                return format!("PACE/general_authenticate_step{}", &step[2..]);
            }
            return format!("PACE/{}", step);
        }
        let fail_on = p["injection"]["pace_fail_on"].as_str();
        if p["card_access_hex"].as_str().unwrap_or("").is_empty() || fail_on.is_none() {
            return String::new();
        }
        return format!("PACE/{}", fail_on.unwrap());
    }
    if mechanism == "AA" {
        if vsc {
            return if p["vsmartcard"]["aa_sw"].as_str().unwrap_or("").is_empty() { String::new() } else { "AA/internal_authenticate".into() };
        }
        return p["aa_injection"]["aa_fail_on"].as_str().map(|f| format!("AA/{}", f)).unwrap_or_default();
    }
    String::new()
}

fn git(dir: &str, args: &[&str]) -> Option<String> {
    let o = Command::new("git").arg("-C").arg(dir).args(args).output().ok()?;
    if o.status.success() { Some(String::from_utf8_lossy(&o.stdout).trim().to_string()) } else { None }
}

fn provenance(root: &str, profile_path: &str, a: &HashMap<String, String>, variant: &str) -> Value {
    let full = fs::canonicalize(profile_path).map(|p| p.to_string_lossy().to_string()).unwrap_or_else(|_| profile_path.into());
    let rel = full.strip_prefix(&format!("{}/", root)).map(|s| s.to_string()).unwrap_or_else(|| profile_path.into());
    let sha = Command::new("sha256sum").arg(&full).output().ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).split(' ').next().unwrap_or("").to_string()).unwrap_or_default();
    let captured = match std::env::var("SOURCE_DATE_EPOCH").ok().and_then(|s| s.parse::<u64>().ok()) {
        Some(e) => e,
        None => SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs(),
    };
    let num = |k: &str, d: u64| a.get(k).and_then(|s| s.parse::<u64>().ok()).unwrap_or(d);
    json!({
        "harness_commit": git(root, &["rev-parse", "HEAD"]).unwrap_or_else(|| "unknown".into()),
        "harness_dirty": !git(root, &["status", "--porcelain", "--untracked-files=no"]).unwrap_or_default().is_empty(),
        "passauf_commit": git(&format!("{}/../_vendor/passauf", root), &["rev-parse", "HEAD"]),
        "rust_version": env!("DRIVER_RUSTC_VERSION"),
        "profile_path": rel,
        "profile_sha256": sha,
        "suite_id": a.get("-suite-id").cloned().unwrap_or_default(),
        "suite_seed": num("-suite-seed", 1),
        "suite_n": num("-suite-n", 1),
        "run_index": num("-run-index", 1),
        "driver": "rust/passauf_read",
        "variant": variant,
        "caller_options": null,
        "captured_at_utc": utc(captured),
    })
}

fn utc(secs: u64) -> String {
    // civil-from-days (Howard Hinnant), enough for an ISO timestamp without a date crate
    let days = (secs / 86400) as i64;
    let rem = secs % 86400;
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z", y, m, d, rem / 3600, (rem % 3600) / 60, rem % 60)
}

fn check_vectors(path: &str) -> i32 {
    let rows: Vec<Value> = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    let mut failures = 0;
    for row in &rows {
        let i = &row["input"];
        let b = |k: &str| i[k].as_bool().unwrap_or(false);
        let o = Observation { fired: b("fired"), failed: b("failed"), succeeded: b("succeeded"),
            returned_error: b("returned_error"), status_signal: b("status_signal") };
        let got = classify(&o);
        if got != row["outcome"].as_str().unwrap_or("") || score(got) != row["score"] {
            eprintln!("vector {}: got {}", row["id"], got);
            failures += 1;
        }
    }
    println!("{}", if failures == 0 { "vectors OK".to_string() } else { format!("{} vector(s) failed", failures) });
    if failures == 0 { 0 } else { 1 }
}
