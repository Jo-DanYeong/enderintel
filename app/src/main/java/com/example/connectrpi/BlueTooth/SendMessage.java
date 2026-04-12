package com.example.connectrpi.BlueTooth;

import android.util.Log;
import android.widget.EditText;
import android.widget.Toast;

import com.example.connectrpi.MainActivity;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class SendMessage {
    private final MainActivity activity;
    private final OutputStream os;
    private final EditText et;
    private final boolean isConnected;

    public SendMessage(MainActivity activity, OutputStream os, EditText et, boolean isConnected) {
        this.activity = activity;
        this.os = os;
        this.et = et;
        this.isConnected = isConnected;
    }

    public void sendMessage() {
        // os가 null이거나 연결 상태가 false면 차단
        if (os == null || !isConnected) {
            Toast.makeText(activity, "연결 상태를 확인하세요!", Toast.LENGTH_SHORT).show();
            return;
        }

        new Thread(() -> {
            try {
                String msg = et.getText().toString() + "\n";
                os.write(msg.getBytes(StandardCharsets.UTF_8));
                os.flush();
                Log.d("BT_LOG", "전송 완료: " + msg);

                activity.runOnUiThread(() -> et.setText(""));
            } catch (IOException e) {
                Log.e("BT_LOG", "전송 실패", e);
                activity.runOnUiThread(() -> Toast.makeText(activity, "전송 실패!", Toast.LENGTH_SHORT).show());
            }
        }).start();
    }
}