const {Pool} = require('pg');

//setup postgres connection with environment variables
const pool =new Pool({
  connectionString: process.env.DATABASE_URL || `postgresql://${process.env.DB_USER}:${process.env.DB_PASSWORD}@${process.env.DB_HOST}:${process.env.DB_PORT || 5432}/${process.env.DB_NAME}`
});

//log when we connect successfully
pool.on('connect',() => {
  console.log('Connected to database');
});

//if connection fails, exit the app
pool.on('error',(err)=>{
  console.error('Database connection error:', err);
  process.exit(-1);
});

//cretes the videos table in postgres
async function createVideosTable() {
  const query=`
    CREATE TABLE IF NOT EXISTS videos (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      prompt TEXT NOT NULL,
      title TEXT,
      style TEXT NOT NULL,
      status TEXT DEFAULT 'queued',
      video_url TEXT,
      thumbnail_url TEXT,
      created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
    CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(created_at DESC);
    ALTER TABLE videos ADD COLUMN IF NOT EXISTS title TEXT;
    ALTER TABLE videos ADD COLUMN IF NOT EXISTS logs TEXT[] DEFAULT '{}';
  `;

  try {
    await pool.query(query);
    console.log('Videos table created');
    return { success: true };
  } catch (error) {
    console.error('Error creating table:', error.message);
    throw error;
  }
}

//inserts a new job into the database and returns the job id
async function insertJob(prompt, style) {
  const query =`
    INSERT INTO videos (prompt, style)
    VALUES ($1, $2)
    RETURNING id;
  `;

  try {
    const result = await pool.query(query, [prompt, style]);
    const jobId = result.rows[0].id;
    console.log('Job inserted with ID:', jobId);
    return jobId;
  } catch (error) {
    console.error('Error inserting job:', error.message);
    throw error;
  }
}

//updates the job status and optionally the video/thumbnail urls
async function updateJobStatus(id, status, videoUrl = null, thumbnailUrl = null) {
  const query = `
    UPDATE videos
    SET status = $1,
        video_url = COALESCE($2, video_url),
        thumbnail_url = COALESCE($3, thumbnail_url)
    WHERE id = $4
    RETURNING id;
  `;

  try {
    const result = await pool.query(query, [status, videoUrl, thumbnailUrl, id]);
    
    if (result.rowCount === 0) {
      throw new Error('Job not found');
    }
    console.log('Job status updated:', id);
    return { success: true };
  } catch (error) {
    console.error('Error updating job:', error.message);
    throw error;
  }
}

//gets a single job by its id
async function getJobById(id){
  const query = `
    SELECT id, prompt, style, status, video_url, thumbnail_url, created_at
    FROM videos
    WHERE id = $1;
  `;

  try {
    const result = await pool.query(query, [id]);
    
    //return null if no job found
    if (result.rows.length === 0) {
      return null;
    }
    return result.rows[0];
  } catch (error) {
    console.error('Error getting job:', error.message);
    throw error;
  }
}
//gets all completed videos for the community feed, with optional search filter
async function getRecentCompletedVideos(search = null) {
  const params = [];
  let whereClause = `WHERE status = 'done'`;

  if (search && search.trim()) {
    params.push(`%${search.trim()}%`);
    whereClause += ` AND (title ILIKE $1 OR prompt ILIKE $1)`;
  }

  const query = `
    SELECT id, COALESCE(title, prompt) AS display_title, prompt, title, style, video_url, thumbnail_url, created_at
    FROM videos
    ${whereClause}
    ORDER BY created_at DESC;
  `;

  try {
    const result = await pool.query(query, params);
    return result.rows;
  } catch (error) {
    console.error('Error getting completed videos:', error.message);
    throw error;
  }
}

//inserts a pre-completed video record (for admin uploads of migrated videos)
async function insertCompletedVideo(prompt, title, videoUrl, thumbnailUrl) {
  const query = `
    INSERT INTO videos (prompt, title, style, status, video_url, thumbnail_url)
    VALUES ($1, $2, 'Uploaded', 'done', $3, $4)
    RETURNING id;
  `;
  try {
    const result = await pool.query(query, [prompt || title, title, videoUrl, thumbnailUrl]);
    const videoId = result.rows[0].id;
    console.log('Uploaded video inserted with ID:', videoId);
    return videoId;
  } catch (error) {
    console.error('Error inserting uploaded video:', error.message);
    throw error;
  }
}

//deletes a video by id
async function deleteVideoById(id) {
  const query = `DELETE FROM videos WHERE id = $1 RETURNING id;`;
  try {
    const result = await pool.query(query, [id]);
    if (result.rowCount === 0) throw new Error('Video not found');
    console.log(`Deleted video: ${id}`);
    return { success: true };
  } catch (error) {
    console.error('Error deleting video:', error.message);
    throw error;
  }
}

//updates the display title of a video
async function updateVideoTitle(id, title) {
  const query = `UPDATE videos SET title = $1 WHERE id = $2 RETURNING id;`;
  try {
    const result = await pool.query(query, [title, id]);
    if (result.rowCount === 0) throw new Error('Video not found');
    return { success: true };
  } catch (error) {
    console.error('Error updating title:', error.message);
    throw error;
  }
}

//appends a log line to a job's logs array
async function appendJobLog(id, message) {
  const query = `
    UPDATE videos
    SET logs = array_append(logs, $1)
    WHERE id = $2;
  `;
  try {
    await pool.query(query, [`[${new Date().toISOString()}] ${message}`, id]);
  } catch (error) {
    console.error('Error appending log:', error.message);
  }
}

//gets the logs array for a job
async function getJobLogs(id) {
  const query = `SELECT logs FROM videos WHERE id = $1;`;
  try {
    const result = await pool.query(query, [id]);
    if (result.rows.length === 0) return [];
    return result.rows[0].logs || [];
  } catch (error) {
    console.error('Error getting logs:', error.message);
    return [];
  }
}

//deletes videos by prompt text
async function deleteVideosByPrompt(prompt) {
  const query = `
    DELETE FROM videos
    WHERE prompt = $1
    RETURNING id;
  `;

  try {
    const result = await pool.query(query, [prompt]);
    console.log(`Deleted ${result.rowCount} video(s) with prompt: "${prompt}"`);
    return { success: true, deletedCount: result.rowCount };
  } catch (error) {
    console.error('Error deleting videos:', error.message);
    throw error;
  }
}

//cleanup function to close the database connection
async function closePool() {
  try {
    await pool.end();
    console.log('Database connection closed');
  } catch (error) {
    console.error('Error closing connection:', error.message);
  }
}

module.exports = {
  pool,
  createVideosTable,
  insertJob,
  insertCompletedVideo,
  updateJobStatus,
  getJobById,
  getJobLogs,
  appendJobLog,
  getRecentCompletedVideos,
  deleteVideoById,
  updateVideoTitle,
  deleteVideosByPrompt,
  closePool
};