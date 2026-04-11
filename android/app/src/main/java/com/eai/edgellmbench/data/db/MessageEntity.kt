package com.eai.edgellmbench.data.db

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Represents a single chat message within a [ConversationEntity].
 * Used for future conversation-history persistence (currently scaffolded).
 */
@Entity(
    tableName = "messages",
    foreignKeys = [
        ForeignKey(
            entity        = ConversationEntity::class,
            parentColumns = ["id"],
            childColumns  = ["conversationId"],
            onDelete      = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("conversationId")],
)
data class MessageEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val conversationId: Long,
    val role: String,          // "user" | "assistant" | "system"
    val content: String,
    val timestamp: Long = System.currentTimeMillis(),
)
