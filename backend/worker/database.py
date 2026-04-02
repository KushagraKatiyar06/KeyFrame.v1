import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool

# load environment variables
load_dotenv()

# get database url from environment variable
DATABASE_URL = os.getenv('DATABASE_URL')

# create a connection pool for better performance
connection_pool = None

def init_pool():
    """Initialize the connection pool"""
    global connection_pool
    if connection_pool is None:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,  # min and max connections
            DATABASE_URL
        )

def get_connection():
    """Get a connection from the pool"""
    try:
        init_pool()
        return connection_pool.getconn()
    except Exception as e:
        print(f"Error getting database connection: {e}")
        raise

def release_connection(conn):
    """Return a connection to the pool"""
    if connection_pool:
        connection_pool.putconn(conn)

def update_job_status(job_id, status):
    """Update the status of a job"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # update the status in the database
        query = "UPDATE videos SET status = %s WHERE id = %s"
        cursor.execute(query, (status, job_id))
        
        # commit the transaction
        conn.commit()
        cursor.close()
        
        print(f"Job {job_id} status updated to: {status}")
        return True
        
    except Exception as e:
        # rollback if there's an error
        if conn:
            try:
                conn.rollback()
            except:
                pass
        print(f"Error updating job status: {e}")
        return False
        
    finally:
        # always return the connection to the pool
        if conn:
            release_connection(conn)

def append_job_log(job_id, message):
    """Append a timestamped log line to the job's logs array"""
    import datetime
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
        line = f"[{timestamp}] {message}"
        query = "UPDATE videos SET logs = array_append(logs, %s) WHERE id = %s"
        cursor.execute(query, (line, job_id))
        conn.commit()
        cursor.close()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        print(f"Error appending log: {e}")
    finally:
        if conn:
            release_connection(conn)

def update_job_completed(job_id, video_url, thumbnail_url):
    """Update job to done status with video and thumbnail URLs"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # update status to done and set the URLs
        query = """
            UPDATE videos 
            SET status = %s, video_url = %s, thumbnail_url = %s 
            WHERE id = %s
        """
        cursor.execute(query, ('done', video_url, thumbnail_url, job_id))
        
        # commit the transaction
        conn.commit()
        cursor.close()
        
        print(f"Job {job_id} completed with video URL: {video_url}")
        return True
        
    except Exception as e:
        # rollback if there's an error
        if conn:
            try:
                conn.rollback()
            except:
                pass
        print(f"Error marking job as completed: {e}")
        return False
        
    finally:
        # always return the connection to the pool
        if conn:
            release_connection(conn)
            