package com.eai.baseline;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

public class MainActivity extends Activity {
    private final BaselineInferenceWrapper inferenceWrapper = new BaselineInferenceWrapper();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        EditText modelPathInput = findViewById(R.id.modelPathInput);
        EditText tokenizerPathInput = findViewById(R.id.tokenizerPathInput);
        EditText promptInput = findViewById(R.id.promptInput);
        TextView statusOutput = findViewById(R.id.statusOutput);
        Button runOnceButton = findViewById(R.id.runOnceButton);

        runOnceButton.setOnClickListener(view -> {
            String modelPath = modelPathInput.getText().toString();
            String tokenizerPath = tokenizerPathInput.getText().toString();
            String prompt = promptInput.getText().toString();

            runOnceButton.setEnabled(false);
            statusOutput.setText(R.string.running_status);

            new Thread(() -> {
                try {
                    String result = inferenceWrapper.runOnce(modelPath, tokenizerPath, prompt);
                    runOnUiThread(() -> {
                        statusOutput.setText(result);
                        runOnceButton.setEnabled(true);
                    });
                } catch (BaselineInferenceWrapper.InferenceException exc) {
                    runOnUiThread(() -> {
                        statusOutput.setText(exc.getCode() + ": " + exc.getMessage());
                        runOnceButton.setEnabled(true);
                    });
                }
            }).start();
        });
    }
}
