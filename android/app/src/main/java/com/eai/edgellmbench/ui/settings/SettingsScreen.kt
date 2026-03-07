package com.eai.edgellmbench.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: SettingsViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    val localContext = LocalContext.current

    Scaffold(
        topBar = { TopAppBar(title = { Text("Settings") }) },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ── Inference settings ───────────────────────────────────────────

            SettingsSection(title = "Inference") {
                // Thread count — discrete: 1, 2, 4, 8 (maps to Pixel 6a big.LITTLE clusters)
                DropdownSetting(
                    label = "Thread count",
                    options = listOf(1, 2, 4, 8),
                    selected = uiState.threadCount,
                    onSelect = { viewModel.setThreadCount(it) },
                    displayFn = { "$it thread${if (it != 1) "s" else ""}" },
                )
                Text(
                    text = "Pixel 6a: 2× Cortex-X1 (big) + 2× A76 + 4× A55 (LITTLE)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                HorizontalDivider()

                // Context length
                DropdownSetting(
                    label = "Context length (tokens)",
                    options = listOf(256, 512, 1024, 2048),
                    selected = uiState.contextLength,
                    onSelect = { viewModel.setContextLength(it) },
                    displayFn = { it.toString() },
                )

                HorizontalDivider()

                // Output length
                DropdownSetting(
                    label = "Max output tokens",
                    options = listOf(32, 64, 128, 256, 512),
                    selected = uiState.outputLength,
                    onSelect = { viewModel.setOutputLength(it) },
                    displayFn = { it.toString() },
                )

                HorizontalDivider()

                // Temperature
                SliderSetting(
                    label = "Temperature",
                    value = uiState.temperature,
                    valueRange = 0f..1f,
                    steps = 9,
                    onValueChange = { viewModel.setTemperature(it) },
                    displayValue = "%.1f".format(uiState.temperature),
                    sublabel = "0.0 = deterministic · 1.0 = creative",
                )

                HorizontalDivider()

                // Seed
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(0.6f)) {
                        Text("Random seed", style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "Fixed seed → reproducible outputs",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    var seedText by remember { mutableStateOf(uiState.seed.toString()) }
                    OutlinedTextField(
                        value = seedText,
                        onValueChange = { v ->
                            seedText = v
                            v.toIntOrNull()?.let { viewModel.setSeed(it) }
                        },
                        singleLine = true,
                        modifier = Modifier.weight(0.35f),
                        textStyle = MaterialTheme.typography.bodyMedium,
                    )
                }

                HorizontalDivider()

                // Apply & Reconfigure — wires thread count, temperature, seed to the live engine
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            "Apply to live engine",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        uiState.applyResult?.let { result ->
                            Text(
                                text = result,
                                style = MaterialTheme.typography.bodySmall,
                                color = if (result.startsWith("Error"))
                                    MaterialTheme.colorScheme.error
                                else
                                    MaterialTheme.colorScheme.primary,
                            )
                        }
                        if (uiState.applyResult == null) {
                            Text(
                                "Resets KV cache — clears conversation",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    if (uiState.isApplying) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(8.dp))
                    }
                    Button(
                        onClick = { viewModel.applySettings(localContext) },
                        enabled = !uiState.isApplying,
                    ) {
                        Text("Apply")
                    }
                }
            }

            // ── Benchmark settings ────────────────────────────────────────────

            SettingsSection(title = "Benchmark") {
                // Warmup runs
                DropdownSetting(
                    label = "Warmup runs",
                    options = listOf(0, 1, 2),
                    selected = uiState.warmupRuns,
                    onSelect = { viewModel.setWarmupRuns(it) },
                    displayFn = { "$it run${if (it != 1) "s" else ""}" },
                )
                Text(
                    text = "Warmup runs are excluded from metrics",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                HorizontalDivider()

                // Benchmark trials
                DropdownSetting(
                    label = "Benchmark trials",
                    options = listOf(3, 5, 10),
                    selected = uiState.benchRuns,
                    onSelect = { viewModel.setBenchRuns(it) },
                    displayFn = { "$it trial${if (it != 1) "s" else ""}" },
                )
                Text(
                    text = "More trials → lower variance, longer run time",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // ── Extensibility stubs ───────────────────────────────────────────

            SettingsSection(title = "Coming Soon") {
                ComingSoonItem(
                    "RAG / Document Chat",
                    "Attach PDFs; inject top-k chunks into system prompt",
                )
                HorizontalDivider()
                ComingSoonItem(
                    "Voice Input",
                    "Whisper-based speech-to-text pipeline",
                )
                HorizontalDivider()
                ComingSoonItem(
                    "Conversation History",
                    "Room DB persistence — browse past sessions",
                )
                HorizontalDivider()
                ComingSoonItem(
                    "GPU Backend",
                    "Vulkan compute via llama.cpp ggml-vulkan.so",
                )
            }

            // ── About ─────────────────────────────────────────────────────────

            SettingsSection(title = "About") {
                AboutRow("App version", "1.0")
                HorizontalDivider()
                AboutRow("Inference backend", "llama.cpp (NDK arm64-v8a)")
                HorizontalDivider()
                AboutRow("Model family", "Llama 3.2 3B Instruct GGUF")
                HorizontalDivider()
                AboutRow("Device target", "Pixel 6a · Google Tensor G2 · 6 GB LPDDR5")
                HorizontalDivider()
                AboutRow("Min SDK", "API 33 (Android 13)")
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}

// ── Section wrapper ────────────────────────────────────────────────────────────

@Composable
private fun SettingsSection(title: String, content: @Composable () -> Unit) {
    Column {
        Text(
            text = title.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                content()
            }
        }
    }
}

// ── Slider setting ────────────────────────────────────────────────────────────

@Composable
private fun SliderSetting(
    label: String,
    value: Float,
    valueRange: ClosedFloatingPointRange<Float>,
    steps: Int,
    onValueChange: (Float) -> Unit,
    displayValue: String,
    sublabel: String = "",
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(label, style = MaterialTheme.typography.bodyMedium)
                if (sublabel.isNotEmpty()) {
                    Text(
                        sublabel,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Text(displayValue, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        }
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = valueRange,
            steps = steps,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

// ── Dropdown setting ──────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> DropdownSetting(
    label: String,
    options: List<T>,
    selected: T,
    onSelect: (T) -> Unit,
    displayFn: (T) -> String,
) {
    var expanded by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = !expanded },
            modifier = Modifier.weight(0.45f),
        ) {
            OutlinedTextField(
                value = displayFn(selected),
                onValueChange = {},
                readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier.menuAnchor(),
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyMedium,
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
            ) {
                options.forEach { option ->
                    DropdownMenuItem(
                        text = { Text(displayFn(option)) },
                        onClick = { onSelect(option); expanded = false },
                    )
                }
            }
        }
    }
}

// ── Coming soon item ──────────────────────────────────────────────────────────

@Composable
private fun ComingSoonItem(title: String, description: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium)
            Text(
                description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            text = "Soon",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.tertiary,
        )
    }
}

// ── About row ─────────────────────────────────────────────────────────────────

@Composable
private fun AboutRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
    }
}
