// One oracle observation against dmrtd: start a chip (harness chip-serve or the independent
// vsmartcard chip), run the read routine of dmrtd's example application, and record the
// caller-boundary outcome. dmrtd makes the caller choose PACE or BAC up front and reports a
// failed step by throwing; the example routine lets that exception reach the application.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dmrtd/src/com/com_provider.dart';
import 'package:dmrtd/src/lds/efcard_access.dart';
import 'package:dmrtd/src/passport.dart';
import 'package:dmrtd/src/proto/dba_key.dart';
import 'package:logging/logging.dart';

// ---------------------------------------------------------------- oracle

class Observation {
  final bool fired, failed, succeeded, returnedError, statusSignal;
  Observation(this.fired, this.failed, this.succeeded, this.returnedError, this.statusSignal);
}

/// Same predicate as classifier/observability.go, .py, Observability.java and Oracle.cs.
String classify(Observation o) {
  if (o.failed && o.succeeded) return 'invalid';
  if (!o.fired) return 'not_applicable';
  if (o.returnedError) return 'surfaced';
  if (o.statusSignal) return 'status_only';
  return 'silent';
}

int? score(String outcome) => const {'silent': 0, 'status_only': 1, 'surfaced': 2}[outcome];

String meaning(String outcome) => const {
      'silent': 'silent: call succeeded, failure not reachable by the caller',
      'status_only': 'status-only: call succeeded, failure recorded in a returned status field',
      'surfaced': 'surfaced: error returned or thrown to the caller',
      'not_applicable': 'not applicable: injected failure did not fire',
    }[outcome] ??
    'invalid: library reported the step as both failed and successful';

// ---------------------------------------------------------------- transport

/// Acts as the reader for a chip process speaking the vpcd socket protocol. Mirrors
/// simulator/vpcd_peer.go, VsmartcardCardService.java and VpcdTransport.cs.
class VpcdProvider extends ComProvider {
  final String executable;
  final List<String> Function(int port) argsForPort;
  final trace = <Map<String, Object>>[];
  ServerSocket? _server;
  Socket? _socket;
  Process? _chip;
  final _buffer = BytesBuilder();
  final _waiters = <Completer<void>>[];

  VpcdProvider(this.executable, this.argsForPort) : super(Logger('vpcd'));

  @override
  Future<void> connect() async {
    _server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    _chip = await Process.start(executable, argsForPort(_server!.port), mode: ProcessStartMode.inheritStdio);
    _socket = await _server!.first.timeout(const Duration(seconds: 30));
    _socket!.listen((data) {
      _buffer.add(data);
      for (final w in List.of(_waiters)) {
        w.complete();
      }
      _waiters.clear();
    });
    _send(Uint8List.fromList([0x01]));
    _send(Uint8List.fromList([0x04]));
    await _receive();
  }

  void _send(Uint8List msg) {
    final hdr = ByteData(2)..setUint16(0, msg.length);
    _socket!.add(hdr.buffer.asUint8List());
    _socket!.add(msg);
  }

  Future<Uint8List> _receive() async {
    final deadline = DateTime.now().add(const Duration(seconds: 30));
    while (true) {
      final bytes = _buffer.toBytes();
      if (bytes.length >= 2) {
        final len = ByteData.sublistView(bytes, 0, 2).getUint16(0);
        if (bytes.length >= 2 + len) {
          final msg = Uint8List.fromList(bytes.sublist(2, 2 + len));
          _buffer.clear();
          _buffer.add(bytes.sublist(2 + len));
          return msg;
        }
      }
      if (DateTime.now().isAfter(deadline)) throw ComProviderError('chip did not answer');
      final w = Completer<void>();
      _waiters.add(w);
      await w.future.timeout(const Duration(seconds: 30), onTimeout: () {});
    }
  }

  @override
  Future<Uint8List> transceive(final Uint8List data) async {
    _send(data);
    final rsp = await _receive();
    final ok = rsp.length >= 2 && rsp[rsp.length - 2] == 0x90 && rsp[rsp.length - 1] == 0x00;
    trace.add({'label': 'INS ${data[1].toRadixString(16).padLeft(2, '0').toUpperCase()}', 'capdu': _hex(data), 'rapdu': _hex(rsp), 'success': ok});
    return rsp;
  }

  @override
  bool isConnected() => _socket != null;

  @override
  Future<void> disconnect() async {
    try {
      _send(Uint8List.fromList([0x00]));
      await _socket?.flush();
    } catch (_) {}
    await _socket?.close();
    await _server?.close();
    _socket = null;
    await _chip?.exitCode.timeout(const Duration(seconds: 5), onTimeout: () {
      _chip?.kill();
      return -1;
    });
  }
}

String _hex(List<int> b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join().toUpperCase();

// ---------------------------------------------------------------- driver

DateTime _yymmdd(String s, {required bool birth}) {
  final yy = int.parse(s.substring(0, 2));
  final year = birth ? (yy > 30 ? 1900 + yy : 2000 + yy) : (yy > 70 ? 1900 + yy : 2000 + yy);
  return DateTime.utc(year, int.parse(s.substring(2, 4)), int.parse(s.substring(4, 6)));
}

Future<void> main(List<String> argv) async {
  exitCode = await _run(argv);
}

Future<int> _run(List<String> argv) async {
  final a = _parse(argv);
  if (a.containsKey('-check-vectors')) return _checkVectors(a['-check-vectors']!);

  final root = Directory.current.path;
  final profilePath = a['-profile']!;
  final profile = jsonDecode(File(profilePath).readAsStringSync()) as Map<String, dynamic>;
  final id = profile['id'] as String;
  final mechanism = (profile['mechanism'] as String? ?? '').toUpperCase();
  final mrz = profile['mrz'] as Map<String, dynamic>;
  final vsc = profile['peer'] == 'vsmartcard';
  final variant = a['-variant'] ?? 'default';
  final report = '${Directory.systemTemp.path}/chip-report-${DateTime.now().microsecondsSinceEpoch}-$pid.json';

  final provider = vsc
      ? VpcdProvider('python3',
          (p) => ['$root/tools/vsmartcard/emrtd_card.py', '--port', '$p', '--profile', profilePath, '--report', report])
      : VpcdProvider(a['-chip-serve'] ?? 'bin/chip-serve', (p) => ['-profile', profilePath, '-port', '$p', '-report', report]);

  var stepFailed = false, stepSucceeded = false, accessControl = '';
  var readErr = '';
  try {
    await provider.connect();
    final passport = Passport(provider);
    EfCardAccess? cardAccess;
    try {
      cardAccess = await passport.readEfCardAccess();
    } catch (_) {
      cardAccess = null; // no EF.CardAccess: BAC-only chip
    }
    final dob = _yymmdd(mrz['date_of_birth'] as String, birth: true);
    final doe = _yymmdd(mrz['date_of_expiry'] as String, birth: false);
    final usePace = cardAccess != null && cardAccess.isPaceInfoSet;
    if (usePace) {
      try {
        await passport.startSessionPACE(DBAKey(mrz['document_number'] as String, dob, doe, paceMode: true), cardAccess);
        if (mechanism == 'PACE') stepSucceeded = true;
      } catch (_) {
        if (mechanism == 'PACE') stepFailed = true;
        rethrow; // the example application lets the exception reach the user
      }
      accessControl = 'PACE';
    } else {
      await passport.startSession(DBAKey(mrz['document_number'] as String, dob, doe));
      accessControl = 'BAC';
    }
    await passport.readEfCOM();
    if (mechanism == 'AA') {
      try {
        await passport.activeAuthenticate(Uint8List.fromList([1, 2, 3, 4, 5, 6, 7, 8]));
        stepSucceeded = true;
      } catch (_) {
        stepFailed = true;
        rethrow;
      }
    }
  } catch (e) {
    readErr = '${e.runtimeType}: $e';
  } finally {
    await provider.disconnect();
  }

  var fired = false;
  final reportFile = File(report);
  if (reportFile.existsSync()) {
    final r = jsonDecode(reportFile.readAsStringSync()) as Map<String, dynamic>;
    fired = ((r['fault_delivered'] as Map<String, dynamic>?) ?? {})[mechanism] == true;
    reportFile.deleteSync();
  }

  final obs = Observation(fired, stepFailed, stepSucceeded, readErr.isNotEmpty, false);
  final outcome = classify(obs);
  final runIndex = int.parse(a['-run-index'] ?? '1');
  final runId = '$id-dmrtd-$variant-${DateTime.now().toUtc().microsecondsSinceEpoch}-${runIndex.toString().padLeft(6, '0')}';
  final result = {
    'run_id': runId,
    'test_case': id,
    'library': 'dmrtd',
    'mechanism': mechanism,
    'condition': profile['condition'],
    'tier': profile['tier'] ?? 'wire',
    'variant': variant,
    'provenance': await _provenance(root, profilePath, a, variant),
    'outcome': outcome,
    'observability_score': score(outcome),
    'observability_meaning': meaning(outcome),
    'observation': {
      'fired': obs.fired,
      'failed': obs.failed,
      'succeeded': obs.succeeded,
      'returned_error': obs.returnedError,
      'status_signal': obs.statusSignal,
    },
    'fault_point': _faultPoint(profile, mechanism, vsc),
    'access_control': accessControl,
    'read_err': readErr,
    'trace': provider.trace,
  };
  final logDir = Directory(a['-log-dir'] ?? 'logs')..createSync(recursive: true);
  File('${logDir.path}/$runId.json').writeAsStringSync('${const JsonEncoder.withIndent('  ').convert(result)}\n');
  stdout.writeln('$id $variant dmrtd: $outcome');
  return 0;
}

String _faultPoint(Map<String, dynamic> p, String mechanism, bool vsc) {
  if (mechanism == 'PACE') {
    if (vsc) {
      // "mse" is PACE/mse_set_at, "gaN" is PACE/general_authenticate_stepN (internal/profile).
      final step = ((p['vsmartcard'] as Map<String, dynamic>?) ?? {})['pace_step'] as String? ?? '';
      if (step.isEmpty) return '';
      if (step == 'mse') return 'PACE/mse_set_at';
      if (step.length == 3 && step.startsWith('ga')) return 'PACE/general_authenticate_step${step.substring(2)}';
      return 'PACE/$step';
    }
    final failOn = (p['injection'] as Map<String, dynamic>?)?['pace_fail_on'] as String?;
    if ((p['card_access_hex'] as String? ?? '').isEmpty || failOn == null) return '';
    return 'PACE/$failOn';
  }
  if (mechanism == 'AA') {
    if (vsc) {
      final sw = ((p['vsmartcard'] as Map<String, dynamic>?) ?? {})['aa_sw'] as String? ?? '';
      return sw.isEmpty ? '' : 'AA/internal_authenticate';
    }
    final failOn = (p['aa_injection'] as Map<String, dynamic>?)?['aa_fail_on'] as String?;
    return failOn == null ? '' : 'AA/$failOn';
  }
  return '';
}

Future<Map<String, Object?>> _provenance(String root, String profilePath, Map<String, String> a, String variant) async {
  Future<String?> git(String dir, List<String> args) async {
    try {
      final r = await Process.run('git', ['-C', dir, ...args]);
      return r.exitCode == 0 ? (r.stdout as String).trim() : null;
    } catch (_) {
      return null;
    }
  }

  final full = File(profilePath).absolute.path;
  final rel = full.startsWith('$root/') ? full.substring(root.length + 1) : profilePath;
  final epoch = int.tryParse(Platform.environment['SOURCE_DATE_EPOCH'] ?? '');
  final captured = epoch != null ? DateTime.fromMillisecondsSinceEpoch(epoch * 1000, isUtc: true) : DateTime.now().toUtc();
  return {
    'harness_commit': (Platform.environment['EMRTD_HARNESS_COMMIT'] ?? '').trim().isNotEmpty
        ? Platform.environment['EMRTD_HARNESS_COMMIT']!.trim()
        : (await git(root, ['rev-parse', 'HEAD']) ?? 'unknown'),
    'harness_dirty': ((await git(root, ['status', '--porcelain', '--untracked-files=no'])) ?? '').isNotEmpty,
    'dmrtd_commit': await git('$root/../_vendor/dmrtd', ['rev-parse', 'HEAD']),
    'dart_version': Platform.version.split(' ').first,
    'profile_path': rel,
    'profile_sha256': await _sha256(full),
    'suite_id': a['-suite-id'] ?? '',
    'suite_seed': int.parse(a['-suite-seed'] ?? '1'),
    'suite_n': int.parse(a['-suite-n'] ?? '1'),
    'run_index': int.parse(a['-run-index'] ?? '1'),
    'driver': 'dart/dmrtd_read',
    'variant': variant,
    'caller_options': null,
    'captured_at_utc': '${captured.toIso8601String().split('.').first}Z',
  };
}

Future<String> _sha256(String path) async {
  final r = await Process.run('sha256sum', [path]);
  return (r.stdout as String).split(' ').first;
}

Map<String, String> _parse(List<String> argv) {
  final out = <String, String>{};
  for (var i = 0; i + 1 < argv.length; i += 2) {
    out[argv[i]] = argv[i + 1];
  }
  return out;
}

int _checkVectors(String path) {
  var failures = 0;
  for (final row in jsonDecode(File(path).readAsStringSync()) as List<dynamic>) {
    final i = row['input'] as Map<String, dynamic>;
    final got = classify(Observation(i['fired'] as bool, i['failed'] as bool, i['succeeded'] as bool,
        i['returned_error'] as bool, i['status_signal'] as bool));
    if (got != row['outcome'] || score(got) != row['score']) {
      stderr.writeln('vector ${row['id']}: got $got');
      failures++;
    }
  }
  stdout.writeln(failures == 0 ? 'vectors OK' : '$failures vector(s) failed');
  return failures == 0 ? 0 : 1;
}
