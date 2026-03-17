package com.eai.edgellmbench.ui.models

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eai.edgellmbench.data.repository.ModelRepository
import androidx.compose.material3.AlertDialog

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelManagerScreen(viewModel: ModelManagerViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    var pendingVariant by remember { mutableStateOf("Q4_K_M") }
    var showF16Warning by remember { mutableStateOf(false) }
    var f16ConfirmedLoad by remember { mutableStateOf(false) }

    // File picker launcher — fallback for models NOT in /data/local/tmp/
    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri -> uri?.let { viewModel.loadFromUri(it, pendingVariant) } }

    LaunchedEffect(uiState.errorMessage) {
        uiState.errorMessage?.let {
            snackbarHostState.showSnackbar(it, duration = SnackbarDuration.Long)
            viewModel.dismissError()
        }
    }

    // Show F16 confirmation dialog if needed
    if (showF16Warning) {
        AlertDialog(
            onDismissRequest = { showF16Warning = false },
            title = { Text("F16 May Cause Out-of-Memory") },
            text = {
                Text(
                    "F16 (full precision, 6.4 GB) is larger than the 6 GB Tensor G1's RAM. " +
                    "Loading may fail or crash the app.\n\n" +
                    "Recommended: Use Q8_0 (3.4 GB, 8-bit) instead for high quality.\n\n" +
                    "Proceed anyway?"
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showF16Warning = false
                        f16ConfirmedLoad = true
                        viewModel.loadFromDevicePath("F16")
                    }
                ) {
                    Text("Load F16 Anyway")
                }
            },
            dismissButton = {
                TextButton(onClick = { showF16Warning = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Model Manager") },
                actions = {
                    IconButton(onClick = { viewModel.refreshDeviceModels() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh device scan")
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
        ) {
            if (uiState.isLoading) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                Text(
                    text = "Loading ${uiState.activeVariant}…",
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // ── How to load hint ─────────────────────────────────────────────
            if (uiState.deviceModels.isEmpty()) {
                ElevatedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            "No models found on device yet",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "Push a model from your Mac:\n" +
                                "  adb push Q4_K_M.gguf \\\n" +
                                "    /data/local/tmp/Llama-3.2-3B-Instruct-Q4_K_M.gguf\n\n" +
                                "Or use  ./scripts/push_models_to_device.sh Q4_K_M\n" +
                                "then tap the Refresh button (↺) above.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            } else {
                Text(
                    text = "${uiState.deviceModels.size} model(s) found in /data/local/tmp/ — tap Load to activate",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                )
            }

            // ── Model list ────────────────────────────────────────────────────
            LazyColumn(
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 16.dp, end = 16.dp, bottom = 16.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(ModelRepository.knownVariants) { info ->
                    val isActive   = uiState.isModelLoaded && uiState.activeVariant == info.name
                    val onDevice   = info.name in uiState.deviceModels

                    Card(
                        colors = if (isActive) CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer,
                        ) else CardDefaults.cardColors(),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {

                            // Title row
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = info.name,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.weight(1f),
                                )
                                if (isActive) {
                                    Icon(
                                        imageVector = Icons.Default.CheckCircle,
                                        contentDescription = "Active",
                                        tint = MaterialTheme.colorScheme.primary,
                                        modifier = Modifier.size(20.dp),
                                    )
                                }
                                if (onDevice && !isActive) {
                                    Icon(
                                        imageVector = Icons.Default.Storage,
                                        contentDescription = "On device",
                                        tint = MaterialTheme.colorScheme.secondary,
                                        modifier = Modifier.size(18.dp),
                                    )
                                }
                            }

                            // Metadata
                            Text(
                                text = "${info.bits}-bit · ~${info.sizeGb} GB" +
                                    if (onDevice) "  •  ✓ on device" else "",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (onDevice)
                                    MaterialTheme.colorScheme.secondary
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            if (info.note.isNotEmpty()) {
                                Text(
                                    text = info.note,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.tertiary,
                                )
                            }

                            Spacer(Modifier.height(10.dp))

                            // Button row
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                // Primary: load from /data/local/tmp/ if already pushed
                                if (onDevice) {
                                    Button(
                                        onClick = {
                                            if (info.name == "F16") {
                                                showF16Warning = true
                                            } else {
                                                viewModel.loadFromDevicePath(info.name)
                                            }
                                        },
                                        enabled = !uiState.isLoading,
                                        modifier = Modifier.weight(1f),
                                    ) {
                                        Icon(
                                            Icons.Default.Storage,
                                            contentDescription = null,
                                            modifier = Modifier.size(16.dp),
                                        )
                                        Spacer(Modifier.width(4.dp))
                                        Text(if (isActive) "Reload" else "Load")
                                    }
                                }

                                // Secondary: open file picker (always available)
                                OutlinedButton(
                                    onClick = {
                                        pendingVariant = info.name
                                        launcher.launch(arrayOf("*/*"))
                                    },
                                    enabled = !uiState.isLoading,
                                    modifier = if (onDevice) Modifier else Modifier.weight(1f),
                                    colors = ButtonDefaults.outlinedButtonColors(),
                                ) {
                                    Icon(
                                        Icons.Default.FolderOpen,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp),
                                    )
                                    Spacer(Modifier.width(4.dp))
                                    Text(if (onDevice) "Browse" else "Load from Files")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
