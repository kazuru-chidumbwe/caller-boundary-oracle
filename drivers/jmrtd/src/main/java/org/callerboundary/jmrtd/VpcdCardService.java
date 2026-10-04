package org.callerboundary.jmrtd;

import net.sf.scuba.smartcards.CardService;
import net.sf.scuba.smartcards.CardServiceException;
import net.sf.scuba.smartcards.CommandAPDU;
import net.sf.scuba.smartcards.ResponseAPDU;
import net.sf.scuba.util.Hex;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.BiFunction;

/**
 * Acts as the reader for a chip process over the vpcd socket protocol (length-prefixed APDUs,
 * one-byte control messages), the same protocol simulator/vpcd_peer.go and the .NET and Dart
 * drivers use. The chip is either the harness chip (cmd/chip-serve) or the independent chip
 * (tools/vsmartcard/emrtd_card.py); both write a delivered-fault report, read by faultDelivered.
 */
public final class VpcdCardService extends CardService {
    private static final long serialVersionUID = 1L;
    private static final byte POWER_OFF = 0x00;
    private static final byte POWER_ON = 0x01;
    private static final byte GET_ATR = 0x04;

    /** One exchanged APDU, as recorded in the run artifact's trace. */
    public static final class TraceEntry {
        public final String label;
        public final String capdu;
        public final String rapdu;
        public final boolean success;

        TraceEntry(String label, String capdu, String rapdu, boolean success) {
            this.label = label;
            this.capdu = capdu;
            this.rapdu = rapdu;
            this.success = success;
        }
    }

    private final Path report;
    private transient Process card;
    private transient ServerSocket server;
    private transient Socket socket;
    private transient DataInputStream in;
    private transient DataOutputStream out;
    private byte[] atr = new byte[0];
    private final List<TraceEntry> trace = new ArrayList<>();

    /** The harness chip: cmd/chip-serve serving the profile. */
    public static VpcdCardService harness(Path chipServe, String profilePath) throws IOException {
        return new VpcdCardService((port, report) -> List.of(chipServe.toString(),
                "-profile", profilePath, "-port", Integer.toString(port), "-report", report.toString()));
    }

    /** The independent chip: the vsmartcard card script serving the profile. */
    public static VpcdCardService independent(Path repoRoot, String profilePath) throws IOException {
        return new VpcdCardService((port, report) -> {
            List<String> cmd = new ArrayList<>(List.of("python3",
                    repoRoot.resolve("tools/vsmartcard/emrtd_card.py").toString(),
                    "--port", Integer.toString(port), "--profile", profilePath, "--report", report.toString()));
            String level = System.getenv("VSMARTCARD_LOG_LEVEL");
            if (level != null && !level.isEmpty()) {
                cmd.add("--log-level");
                cmd.add(level);
            }
            return cmd;
        });
    }

    private VpcdCardService(BiFunction<Integer, Path, List<String>> command) throws IOException {
        report = Files.createTempFile("chip-report-", ".json");
        server = new ServerSocket(0, 1, InetAddress.getLoopbackAddress());
        server.setSoTimeout(30_000);
        card = new ProcessBuilder(command.apply(server.getLocalPort(), report))
                .redirectOutput(ProcessBuilder.Redirect.INHERIT)
                .redirectError(ProcessBuilder.Redirect.INHERIT).start();
        socket = server.accept();
        socket.setSoTimeout(30_000);
        in = new DataInputStream(socket.getInputStream());
        out = new DataOutputStream(socket.getOutputStream());
    }

    private void send(byte[] msg) throws IOException {
        out.writeShort(msg.length);
        out.write(msg);
        out.flush();
    }

    private byte[] recv() throws IOException {
        int len = in.readUnsignedShort();
        byte[] msg = new byte[len];
        in.readFully(msg);
        return msg;
    }

    @Override
    public void open() throws CardServiceException {
        try {
            send(new byte[] {POWER_ON});
            send(new byte[] {GET_ATR});
            atr = recv();
        } catch (IOException e) {
            throw new CardServiceException("chip power-up failed: " + e.getMessage());
        }
    }

    @Override
    public boolean isOpen() {
        return socket != null && !socket.isClosed();
    }

    @Override
    public byte[] getATR() {
        return atr.clone();
    }

    @Override
    public ResponseAPDU transmit(CommandAPDU capdu) throws CardServiceException {
        byte[] rsp;
        try {
            send(capdu.getBytes());
            rsp = recv();
        } catch (IOException e) {
            trace.add(new TraceEntry(String.format("INS %02X", capdu.getINS()), Hex.bytesToHexString(capdu.getBytes()), "", false));
            throw new CardServiceException("chip transport failed: " + e.getMessage());
        }
        trace.add(new TraceEntry(String.format("INS %02X", capdu.getINS()),
                Hex.bytesToHexString(capdu.getBytes()), Hex.bytesToHexString(rsp), rsp.length >= 2
                && (rsp[rsp.length - 2] & 0xFF) == 0x90 && rsp[rsp.length - 1] == 0));
        if (rsp.length < 2) {
            // A channel fault (no response, timeout, transport abort) arrives as an empty frame.
            throw new CardServiceException("no response from chip");
        }
        return new ResponseAPDU(rsp);
    }

    @Override
    public void close() {
        try {
            if (out != null) {
                send(new byte[] {POWER_OFF});
            }
        } catch (IOException ignored) {
            // chip already gone
        }
        try {
            if (socket != null) {
                socket.close();
            }
            if (server != null) {
                server.close();
            }
        } catch (IOException ignored) {
            // nothing left to release
        }
        if (card != null) {
            // cmd/chip-serve writes its delivered-fault report when the session ends: let it exit
            // on its own before forcing it, or the report can be lost.
            try {
                if (!card.waitFor(10, TimeUnit.SECONDS)) {
                    card.destroy();
                    card.waitFor(5, TimeUnit.SECONDS);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                card.destroy();
            }
        }
    }

    @Override
    public boolean isConnectionLost(Exception e) {
        return false;
    }

    public List<TraceEntry> trace() {
        return trace;
    }

    /** Whether the chip sent the injected failure for mechanism, per its delivered-fault report. */
    @SuppressWarnings("unchecked")
    public boolean faultDelivered(String mechanism) {
        try {
            Map<String, Object> r = new com.google.gson.Gson().fromJson(Files.readString(report), Map.class);
            Object d = r == null ? null : r.get("fault_delivered");
            return d instanceof Map<?, ?> m && Boolean.TRUE.equals(m.get(mechanism));
        } catch (IOException | com.google.gson.JsonParseException e) {
            return false;
        }
    }
}
