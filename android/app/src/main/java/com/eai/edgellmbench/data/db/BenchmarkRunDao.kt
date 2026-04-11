package com.eai.edgellmbench.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface BenchmarkRunDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(run: BenchmarkRunEntity)

    /** All runs, newest first. Emits a new list whenever the table changes. */
    @Query("SELECT * FROM benchmark_runs ORDER BY timestamp DESC")
    fun getAllRuns(): Flow<List<BenchmarkRunEntity>>

    @Query("DELETE FROM benchmark_runs WHERE runId = :runId")
    suspend fun delete(runId: String)

    @Query("DELETE FROM benchmark_runs")
    suspend fun deleteAll()
}
