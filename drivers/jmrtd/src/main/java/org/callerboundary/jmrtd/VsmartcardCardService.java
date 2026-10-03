package org.callerboundary.jmrtd;

import net.sf.scuba.smartcards.CardService;
import net.sf.scuba.smartcards.CardServiceException;
import net.sf.scuba.smartcards.CommandAPDU;
import net.sf.scuba.smartcards.ResponseAPDU;
import net.sf.scuba.util.Hex;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Runs tools/vsmartcard/emrtd_card.py (the independent vsmartcard chip) and acts as its
 * reader over the vpcd socket protocol: length-prefixed APDUs, one-byte control messages.
 * Mirrors simulator/vpcd_peer.go.
 */
public final class VsmartcardCardService extends CardService {
    private static final long serialVersionUID = 1L;
    private static final byte POWER_OFF = 0x00;
    private static final byte POWER_ON = 0x01;
    private static final byte GET_ATR = 0x04;

    private final Path report;
    private transient Process card;
    private transient ServerSocket server;
    private transient Socket socket;
    private transient DataInputStream in;
    private transient DataOutputStream out;
    private byte[] atr = new byte[0];
    private final List<PaceFailureCardService.TraceEntry> trace = new ArrayList<>();

    /** Starts the card for the profile at profilePath (its "vsmartcard" object configures the card). */
    public VsmartcardCardService(Path repoRoot, String profilePath) throws IOException {
        report = Files.createTempFile("vsmartcard-report-", ".json");
        server = new ServerSocket(0, 1, InetAddress.getLoopbackAddress());
        server.setSoTimeout(30_000);
        List<String> cmd = new ArrayList<>(List.of("python3",
                repoRoot.resolve("tools/vsmartcard/emrtd_card.py").toString(),
                "--port", Integer.toString(server.getLocalPort()),
                "--profile", profilePath, "--report", report.toString()));
        String level = System.getenv("VSMARTCARD_LOG_LEVEL");
        if (level != null && !level.isEmpty()) {
            cmd.add("--log-level");
            cmd.add(level);
        }
        card = new ProcessBuilder(cmd).redirectOutput(ProcessBuilder.Redirect.INHERIT)
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
            throw new CardServiceException("vsmartcard power-up failed: " + e.getMessage());
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
        try {
            send(capdu.getBytes());
            byte[] rsp = recv();
            ResponseAPDU rapdu = new ResponseAPDU(rsp);
            trace.add(new PaceFailureCardService.TraceEntry(String.format("INS %02X", capdu.getINS()),
                    Hex.bytesToHexString(capdu.getBytes()), Hex.bytesToHexString(rsp), rapdu.getSW() == 0x9000));
            return rapdu;
        } catch (IOException e) {
            throw new CardServiceException("vsmartcard transport failed: " + e.getMessage());
        }
    }

    @Override
    public void close() {
        try {
            if (out != null) {
                send(new byte[] {POWER_OFF});
            }
        } catch (IOException ignored) {
            // card already gone
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
            card.destroy();
            try {
                card.waitFor(5, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    @Override
    public boolean isConnectionLost(Exception e) {
        return false;
    }

    public List<PaceFailureCardService.TraceEntry> trace() {
        return trace;
    }

    /** Whether the card sent the injected failure for mechanism, per its delivered-fault report. */
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
