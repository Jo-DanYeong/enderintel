package com.example.connectrpi.BlueTooth;

import android.annotation.SuppressLint;
import android.widget.TextView;

import com.example.connectrpi.MainActivity;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReceiveData {
    private final MainActivity activity;
    private final InputStream is;
    private final TextView ServerMsg;
    private boolean isRunning;

    public ReceiveData(MainActivity activity, InputStream is, TextView ServerMsg) {
        this.activity = activity;
        this.is = is;
        this.ServerMsg = ServerMsg;
    }

    @SuppressLint("SetTextI18n")
    public void beginListenForData() {
        isRunning = true;
        new Thread(() -> {
            byte[] buffer = new byte[1024];
            while (isRunning && !Thread.currentThread().isInterrupted()) {
                try {
                    // 데이터가 있을 때만 읽기 시도
                    if (is != null && is.available() > 0) {
                        int bytesRead = is.read(buffer);
                        if (bytesRead > 0) {
                            String data = new String(buffer, 0, bytesRead, StandardCharsets.UTF_8);
                            activity.runOnUiThread(() -> ServerMsg.setText(data));
                        }
                    }
                    // CPU 과부하 방지 및 노트북 다운 방지 (중요!)
                    Thread.sleep(10);
                } catch (IOException | InterruptedException e) {
                    isRunning = false;
                    break;
                }
            }
        }).start();
    }
}