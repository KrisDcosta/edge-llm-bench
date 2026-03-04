package com.eai.baseline;

import android.util.Log;

import org.pytorch.executorch.ExecutorchRuntimeException;
import org.pytorch.executorch.extension.llm.LlmCallback;
import org.pytorch.executorch.extension.llm.LlmGenerationConfig;
import org.pytorch.executorch.extension.llm.LlmModule;
import org.pytorch.executorch.extension.llm.LlmModuleConfig;

import java.io.File;
import java.util.Arrays;
import java.util.List;

public final class BaselineInferenceWrapper {
    private static final String TAG = "BaselineInference";
    private static final int MAX_NEW_TOKENS = 16;
    private static final int SEQ_LEN = 256;
    private static final float DEFAULT_TEMPERATURE = 0.0f;
    private static final List<String> DEFAULT_TOKENIZER_FILES = Arrays.asList(
        "tokenizer.model",
        "tokenizer.json",
        "tokenizer.bin",
        "sentencepiece.model",
        "spm.model"
    );

    public String runOnce(String modelPath, String tokenizerPath, String prompt) throws InferenceException {
        String normalizedModelPath = modelPath == null ? "" : modelPath.trim();
        if (normalizedModelPath.isEmpty()) {
            throw new InferenceException(
                "MISSING_MODEL_ARTIFACT",
                "Model path is required before running inference."
            );
        }

        File modelFile = new File(normalizedModelPath);
        if (!modelFile.isFile()) {
            throw new InferenceException(
                "MISSING_MODEL_ARTIFACT",
                "Model artifact not found at: " + normalizedModelPath
            );
        }

        if (!modelFile.canRead()) {
            throw new InferenceException(
                "ARTIFACT_LOAD_FAILURE",
                "Model artifact is not readable: " + normalizedModelPath
            );
        }

        if (!normalizedModelPath.endsWith(".pte")) {
            throw new InferenceException(
                "ARTIFACT_LOAD_FAILURE",
                "Expected an ExecuTorch .pte artifact, got: " + normalizedModelPath
            );
        }

        String normalizedPrompt = prompt == null ? "" : prompt.trim();
        if (normalizedPrompt.isEmpty()) {
            throw new InferenceException(
                "RUNTIME_EXECUTION_FAILURE",
                "Prompt input is required before execution."
            );
        }

        LlmModule module = null;
        String dataPath = modelFile.getParent();
        if (dataPath == null) {
            dataPath = "";
        }

        String resolvedTokenizerPath = resolveTokenizerPath(modelFile, tokenizerPath);
        try {
            LlmModuleConfig config = LlmModuleConfig.create()
                .modulePath(normalizedModelPath)
                .tokenizerPath(resolvedTokenizerPath)
                .dataPath(dataPath)
                .temperature(DEFAULT_TEMPERATURE)
                .modelType(LlmModule.MODEL_TYPE_TEXT)
                .build();
            module = new LlmModule(config);
        } catch (RuntimeException exc) {
            throw new InferenceException(
                "ARTIFACT_LOAD_FAILURE",
                "Failed to initialize ExecuTorch module config: " + exc.getMessage(),
                exc
            );
        }

        try {
            int loadStatus = module.load();
            Log.i(TAG, "loadStatus=" + loadStatus);
            if (loadStatus != ExecutorchRuntimeException.OK) {
                throw new InferenceException(
                    "ARTIFACT_LOAD_FAILURE",
                    "ExecuTorch load failed with status code " + loadStatus + "."
                );
            }

            LlmGenerationConfig generationConfig = LlmGenerationConfig.create()
                .echo(false)
                .warming(false)
                .maxNewTokens(MAX_NEW_TOKENS)
                .seqLen(SEQ_LEN)
                .temperature(DEFAULT_TEMPERATURE)
                .build();

            StringBuilder output = new StringBuilder();
            int generateStatus = module.generate(
                normalizedPrompt,
                generationConfig,
                new LlmCallback() {
                    @Override
                    public void onResult(String text) {
                        if (text != null) {
                            output.append(text);
                        }
                    }
                }
            );
            Log.i(TAG, "generateStatus=" + generateStatus);

            if (generateStatus != ExecutorchRuntimeException.OK) {
                throw new InferenceException(
                    "RUNTIME_EXECUTION_FAILURE",
                    "ExecuTorch generation failed with status code " + generateStatus + "."
                );
            }

            String generated = output.toString().trim();
            if (generated.isEmpty()) {
                throw new InferenceException(
                    "RUNTIME_EXECUTION_FAILURE",
                    "ExecuTorch generation completed without returning output."
                );
            }

            return generated;
        } catch (ExecutorchRuntimeException exc) {
            String code = exc.getErrorCode() == ExecutorchRuntimeException.INVALID_PROGRAM
                || exc.getErrorCode() == ExecutorchRuntimeException.INVALID_EXTERNAL_DATA
                ? "ARTIFACT_LOAD_FAILURE"
                : "RUNTIME_EXECUTION_FAILURE";
            throw new InferenceException(code, exc.getMessage(), exc);
        } catch (UnsatisfiedLinkError exc) {
            throw new InferenceException(
                "RUNTIME_EXECUTION_FAILURE",
                "ExecuTorch native runtime is unavailable: " + exc.getMessage(),
                exc
            );
        } finally {
            if (module != null) {
                module.resetNative();
            }
        }
    }

    private static String resolveTokenizerPath(File modelFile, String tokenizerPath) throws InferenceException {
        String normalizedTokenizerPath = tokenizerPath == null ? "" : tokenizerPath.trim();
        if (!normalizedTokenizerPath.isEmpty()) {
            File tokenizerFile = new File(normalizedTokenizerPath);
            if (!tokenizerFile.isFile()) {
                throw new InferenceException(
                    "ARTIFACT_LOAD_FAILURE",
                    "Tokenizer artifact not found at: " + normalizedTokenizerPath
                );
            }
            if (!tokenizerFile.canRead()) {
                throw new InferenceException(
                    "ARTIFACT_LOAD_FAILURE",
                    "Tokenizer artifact is not readable: " + normalizedTokenizerPath
                );
            }
            return normalizedTokenizerPath;
        }

        File modelDir = modelFile.getParentFile();
        if (modelDir != null) {
            for (String candidate : DEFAULT_TOKENIZER_FILES) {
                File tokenizerCandidate = new File(modelDir, candidate);
                if (tokenizerCandidate.isFile() && tokenizerCandidate.canRead()) {
                    return tokenizerCandidate.getAbsolutePath();
                }
            }
        }

        throw new InferenceException(
            "ARTIFACT_LOAD_FAILURE",
            "Tokenizer artifact is required. Set tokenizer path explicitly or place one of "
                + DEFAULT_TOKENIZER_FILES + " next to the model file."
        );
    }

    public static final class InferenceException extends Exception {
        private final String code;

        InferenceException(String code, String message) {
            super(message);
            this.code = code;
        }

        InferenceException(String code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public String getCode() {
            return code;
        }
    }
}
