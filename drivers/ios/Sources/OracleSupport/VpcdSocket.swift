import Darwin
import Foundation

/// Blocking client for the vpcd socket protocol (length-prefixed messages; one-byte control
/// messages), connected to tools/chip_broker.py on the host. Mirrors simulator/vpcd_peer.go.
public final class VpcdSocket {
    private let fd: Int32
    public private(set) var atr = Data()

    public enum SocketError: Error { case connect(Int32), io(String) }

    /// Connects to the broker and announces the run, then powers the chip up.
    public init(port: UInt16, runId: String, profile: String) throws {
        fd = socket(AF_INET, SOCK_STREAM, 0)
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        let rc = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        guard rc == 0 else { throw SocketError.connect(errno) }
        let header = try JSONSerialization.data(withJSONObject: ["run_id": runId, "profile": profile])
        try send(header)
        try send(Data([0x01]))  // power on
        try send(Data([0x04]))  // get ATR
        atr = try receive()
    }

    public func send(_ msg: Data) throws {
        var out = Data([UInt8(msg.count >> 8), UInt8(msg.count & 0xFF)])
        out.append(msg)
        try out.withUnsafeBytes { buf in
            var sent = 0
            while sent < buf.count {
                let n = Darwin.send(fd, buf.baseAddress! + sent, buf.count - sent, 0)
                guard n > 0 else { throw SocketError.io("send") }
                sent += n
            }
        }
    }

    public func receive() throws -> Data {
        let hdr = try readExactly(2)
        return try readExactly(Int(hdr[0]) << 8 | Int(hdr[1]))
    }

    private func readExactly(_ count: Int) throws -> Data {
        var data = Data(count: count)
        var got = 0
        while got < count {
            let n = data.withUnsafeMutableBytes { recv(fd, $0.baseAddress! + got, count - got, 0) }
            guard n > 0 else { throw SocketError.io("recv") }
            got += n
        }
        return data
    }

    /// Exchanges one command APDU for its response.
    public func transmit(_ apdu: Data) throws -> Data {
        try send(apdu)
        return try receive()
    }

    public func close() {
        try? send(Data([0x00]))  // power off
        Darwin.close(fd)
    }
}
