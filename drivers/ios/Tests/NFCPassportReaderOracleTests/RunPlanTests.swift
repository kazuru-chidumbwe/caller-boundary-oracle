import Foundation
@testable import NFCPassportReader
import OracleSupport
import XCTest

/// Runs every entry of the plan written by tools/ios_plan.py through NFCPassportReader's own read
/// routine (PassportReader.startReading: PACE, fallback to BAC, data groups with CA, then AA) and
/// prints one "CBO-RESULT <json>" line per run. tools/ios_collect.py turns those lines and the
/// broker's chip reports into run artifacts.
final class RunPlanTests: XCTestCase {
    struct Entry: Decodable {
        let run_id: String
        let profile: String
        let mechanism: String
        let mrz_key: String
        let optin: Bool?
    }

    func testRunPlan() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let planPath = env["CBO_PLAN"] else { throw XCTSkip("CBO_PLAN not set") }
        let port = UInt16(env["CBO_BROKER_PORT"] ?? "35963") ?? 35963
        let plan = try JSONDecoder().decode([Entry].self, from: Data(contentsOf: URL(fileURLWithPath: planPath)))

        for entry in plan {
            var result: [String: Any] = ["run_id": entry.run_id]
            do {
                let socket = try VpcdSocket(port: port, runId: entry.run_id, profile: entry.profile)
                let tag = SocketTag(socket: socket)
                let reader = PassportReader()
                reader.mrzKey = entry.mrz_key
                reader.passport = NFCPassportModel()
                reader.dataGroupsToRead = [.COM, .SOD]
                reader.readAllDatagroups = true
                reader.skipPACE = false
                reader.skipCA = false
                reader.skipSecureElements = true
                reader.aaChallenge = [1, 2, 3, 4, 5, 6, 7, 8]
                #if CBO_NFCPR_OPTIN
                if entry.optin == true {
                    reader.allowChipAuthenticationFailure = false
                    reader.allowActiveAuthenticationFailure = false
                }
                #endif
                result["optin"] = entry.optin ?? false
                var readErr = ""
                do {
                    _ = try await reader.startReading(tagReader: TagReader(tag: tag))
                } catch {
                    readErr = "\(error)"
                }
                let p = reader.passport
                result["read_err"] = readErr
                result["pace_status"] = "\(p.PACEStatus)"
                result["chip_authentication_status"] = "\(p.chipAuthenticationStatus)"
                result["active_authentication_supported"] = p.activeAuthenticationSupported
                result["active_authentication_passed"] = p.activeAuthenticationPassed
                result["trace"] = tag.trace
                socket.close()
            } catch {
                result["harness_error"] = "\(error)"
            }
            let line = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
            print("CBO-RESULT " + String(decoding: line, as: UTF8.self))
        }
    }
}
