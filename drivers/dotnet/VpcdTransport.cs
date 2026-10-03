using System.Buffers.Binary;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using Emrtd;

namespace CallerBoundary.EmrtdDotnet;

/// <summary>
/// Acts as the reader for a chip process speaking the vpcd socket protocol (cmd/chip-serve or
/// tools/vsmartcard/emrtd_card.py): length-prefixed messages, one-byte control messages.
/// Mirrors simulator/vpcd_peer.go and VsmartcardCardService.java.
/// </summary>
public sealed class VpcdTransport : ICardTransport
{
    private const byte PowerOff = 0x00, PowerOn = 0x01, Reset_ = 0x02, GetAtr = 0x04;

    private readonly TcpListener _listener;
    private readonly Process _chip;
    private readonly TcpClient _client;
    private readonly NetworkStream _stream;
    public List<(string Label, string Capdu, string Rapdu, bool Success)> Trace { get; } = [];
    public byte[] Atr { get; }

    /// <param name="fileName">chip executable</param>
    /// <param name="argsForPort">builds the chip's arguments for the port it must connect to</param>
    public VpcdTransport(string fileName, Func<int, IEnumerable<string>> argsForPort)
    {
        _listener = new TcpListener(IPAddress.Loopback, 0);
        _listener.Start();
        int port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        var psi = new ProcessStartInfo(fileName) { UseShellExecute = false };
        foreach (string a in argsForPort(port)) psi.ArgumentList.Add(a);
        _chip = Process.Start(psi) ?? throw new InvalidOperationException($"could not start {fileName}");
        var accept = _listener.AcceptTcpClientAsync();
        if (!accept.Wait(TimeSpan.FromSeconds(30))) throw new TimeoutException("chip did not connect");
        _client = accept.Result;
        _client.ReceiveTimeout = 30_000;
        _stream = _client.GetStream();
        Send([PowerOn]);
        Send([GetAtr]);
        Atr = Receive();
    }

    private void Send(byte[] msg)
    {
        Span<byte> hdr = stackalloc byte[2];
        BinaryPrimitives.WriteUInt16BigEndian(hdr, (ushort)msg.Length);
        _stream.Write(hdr);
        _stream.Write(msg);
        _stream.Flush();
    }

    private byte[] Receive()
    {
        byte[] hdr = new byte[2];
        _stream.ReadExactly(hdr);
        byte[] msg = new byte[BinaryPrimitives.ReadUInt16BigEndian(hdr)];
        _stream.ReadExactly(msg);
        return msg;
    }

    public byte[] Transmit(byte[] apdu)
    {
        Send(apdu);
        byte[] rsp = Receive();
        bool ok = rsp.Length >= 2 && rsp[^2] == 0x90 && rsp[^1] == 0x00;
        Trace.Add(($"INS {apdu[1]:X2}", Convert.ToHexString(apdu), Convert.ToHexString(rsp), ok));
        return rsp;
    }

    public void Reset() => Send([Reset_]);

    public void Dispose()
    {
        try { Send([PowerOff]); } catch (IOException) { } catch (ObjectDisposedException) { }
        _client.Dispose();
        _listener.Stop();
        if (!_chip.WaitForExit(5000)) _chip.Kill(entireProcessTree: true);
        _chip.Dispose();
    }
}
