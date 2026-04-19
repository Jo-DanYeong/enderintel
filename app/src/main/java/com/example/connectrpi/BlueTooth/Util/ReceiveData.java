package com.example.connectrpi.BlueTooth.Util;

import android.annotation.SuppressLint;
import android.util.Log;
import android.widget.TextView;
import android.widget.Toast;
import com.example.connectrpi.MainActivity;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReceiveData {
    private final MainActivity activity;
    private final InputStream is;
    private final TextView receiveText;

    public ReceiveData(MainActivity activity, InputStream is, TextView receiveText) {
        this.activity = activity;
        this.is = is;
        this.receiveText = receiveText;
    }

    @SuppressLint("SetTextI18n")
    public void beginListenForData() {
        new Thread(() -> {
            byte[] buffer = new byte[1024];
            Status.setIsRunning(true);

            while (Status.getIsRunning()&&!Thread.currentThread().isInterrupted()) {
                try {
                    int bytesRead = is.read(buffer);

                    if (bytesRead > 0) {
                        String data = new String(buffer, 0, bytesRead, StandardCharsets.UTF_8);
                        activity.runOnUiThread(() -> receiveText.setText(data));
                    } else if (bytesRead == -1) {
                        // 스트림이 닫힌 경우
                        break;
                    }

                } catch (IOException e) {
                    Log.e("BT_LOG", "수신 오류 및 종료", e);
                    activity.runOnUiThread(() -> Toast.makeText(activity, "연결 종료 : 수신중 오류 발생", Toast.LENGTH_SHORT).show());
                    Status.setIsRunning(false);
                    break; // 스레드 종료 후 재연결 프로세스에 의해 새 스레드 생성 유도
                }
            }

        }).start();
    }
}