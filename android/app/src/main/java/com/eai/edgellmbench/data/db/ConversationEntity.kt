package com.eai.edgellmbench.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Represents a conversation session.
 * Used for future conversation-history persistence (currently scaffolded).
 */
@Entity(tableName = "conversations")
data class ConversationEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val quantVariant: String,
    val createdAt: Long = System.currentTimeMillis(),
)
