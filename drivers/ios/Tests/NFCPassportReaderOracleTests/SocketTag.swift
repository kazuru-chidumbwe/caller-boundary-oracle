import CoreNFC
import Foundation
import OracleSupport

/// An NFCISO7816Tag whose APDUs go to a harness chip over the vpcd socket instead of the NFC
/// radio. Only sendCommand carries behaviour; the remaining protocol members are inert.
final class SocketTag: NSObject, NFCISO7816Tag {
    private let socket: VpcdSocket
    private(set) var trace: [[String: Any]] = []

    init(socket: VpcdSocket) {
        self.socket = socket
    }

    // MARK: NFCISO7816Tag

    var initialSelectedAID: String { "A0000002471001" }
    var identifier: Data { Data([0x01, 0x02, 0x03, 0x04]) }
    var historicalBytes: Data? { nil }
    var applicationData: Data? { nil }
    var proprietaryApplicationDataCoding: Bool { false }

    func sendCommand(apdu: NFCISO7816APDU, completionHandler: @escaping (Data, UInt8, UInt8, Error?) -> Void) {
        let encoded = Self.encode(apdu)
        do {
            let rsp = try socket.transmit(encoded)
            guard rsp.count >= 2 else {
                trace.append(["label": String(format: "INS %02X", apdu.instructionCode), "capdu": encoded.hex, "rapdu": rsp.hex, "success": false])
                completionHandler(Data(), 0, 0, NSError(domain: "SocketTag", code: 1, userInfo: [NSLocalizedDescriptionKey: "empty response"]))
                return
            }
            let sw1 = rsp[rsp.count - 2], sw2 = rsp[rsp.count - 1]
            trace.append(["label": String(format: "INS %02X", apdu.instructionCode), "capdu": encoded.hex, "rapdu": rsp.hex,
                          "success": sw1 == 0x90 && sw2 == 0x00])
            completionHandler(rsp.prefix(rsp.count - 2), sw1, sw2, nil)
        } catch {
            completionHandler(Data(), 0, 0, error)
        }
    }

    @available(iOS 14.0, *)
    func sendCommand(apdu: NFCISO7816APDU, resultHandler: @escaping (Result<NFCISO7816ResponseAPDU, Error>) -> Void) {
        sendCommand(apdu: apdu) { data, sw1, sw2, error in
            if let error = error {
                resultHandler(.failure(error))
            } else {
                resultHandler(.success(NFCISO7816ResponseAPDU(data: data, statusWord1: sw1, statusWord2: sw2)))
            }
        }
    }

    /// ISO 7816-4 short or extended encoding of a command APDU.
    static func encode(_ apdu: NFCISO7816APDU) -> Data {
        var out = Data([apdu.instructionClass, apdu.instructionCode, apdu.p1Parameter, apdu.p2Parameter])
        let body = apdu.data ?? Data()
        let le = apdu.expectedResponseLength
        let extended = body.count > 255 || le > 256
        if !body.isEmpty {
            if extended {
                out.append(contentsOf: [0x00, UInt8(body.count >> 8), UInt8(body.count & 0xFF)])
            } else {
                out.append(UInt8(body.count))
            }
            out.append(body)
        }
        if le > 0 {
            if extended {
                if body.isEmpty { out.append(0x00) }
                out.append(contentsOf: le >= 65536 ? [0x00, 0x00] : [UInt8(le >> 8), UInt8(le & 0xFF)])
            } else {
                out.append(le == 256 ? 0x00 : UInt8(le))
            }
        }
        return out
    }

    // MARK: NFCTag / NFCNDEFTag (not used by NFCPassportReader's reading path)

    var type: __NFCTagType { .iso7816Compatible }
    var session: NFCReaderSessionProtocol? { nil }
    var isAvailable: Bool { true }

    func asNFCISO15693Tag() -> NFCISO15693Tag? { nil }
    func asNFCISO7816Tag() -> NFCISO7816Tag? { self }
    func asNFCFeliCaTag() -> NFCFeliCaTag? { nil }
    func asNFCMiFareTag() -> NFCMiFareTag? { nil }

    func queryNDEFStatus(completionHandler: @escaping (NFCNDEFStatus, Int, Error?) -> Void) {
        completionHandler(.notSupported, 0, nil)
    }

    func readNDEF(completionHandler: @escaping (NFCNDEFMessage?, Error?) -> Void) {
        completionHandler(nil, NSError(domain: "SocketTag", code: 2))
    }

    func writeNDEF(_ ndefMessage: NFCNDEFMessage, completionHandler: @escaping (Error?) -> Void) {
        completionHandler(NSError(domain: "SocketTag", code: 2))
    }

    func writeLock(completionHandler: @escaping (Error?) -> Void) {
        completionHandler(NSError(domain: "SocketTag", code: 2))
    }

    static var supportsSecureCoding: Bool { false }
    func encode(with coder: NSCoder) {}
    required init?(coder: NSCoder) { nil }
    func copy(with zone: NSZone? = nil) -> Any { self }
}

extension Data {
    var hex: String { map { String(format: "%02X", $0) }.joined() }
}
