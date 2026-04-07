const express = require('express');
const router = express.Router();
const db = require('../database');

router.get('/:id',async(req, res) => {
  try {
    const {id} = req.params;

    if (!id){
      return res.status(400).json({ 
        error: 'Job ID is required' 
      });}


    const job= await db.getJobById(id);

    if (!job) {
      return res.status(404).json({ 
        error: 'Job not found' 
      });
    }
    
    res.status(200).json({
      id: job.id,
      prompt: job.prompt,
      title: job.title || null,
      style: job.style,
      status: job.status,
      video_url: job.video_url,
      thumbnail_url: job.thumbnail_url,
      created_at: job.created_at
    });
    
  } catch (error) {
    console.error('Error in status route:', error);
    res.status(500).json({ 
      error: 'Failed to get job status' 
    });
  }
});

// GET /api/v1/status/:id/logs — return the pipeline log lines for a job
router.get('/:id/logs', async (req, res) => {
  try {
    const { id } = req.params;
    const logs = await db.getJobLogs(id);
    res.json({ logs });
  } catch (error) {
    console.error('Error in logs route:', error);
    res.status(500).json({ error: 'Failed to get logs' });
  }
});

// PATCH /api/v1/status/:id/title — save video title from the done screen
router.patch('/:id/title', async (req, res) => {
  try {
    const { id } = req.params;
    const { title } = req.body;
    if (!title || !title.trim()) {
      return res.status(400).json({ error: 'title is required' });
    }
    await db.updateVideoTitle(id, title.trim());
    res.json({ success: true });
  } catch (error) {
    console.error('Error saving title:', error);
    res.status(500).json({ error: 'Failed to save title' });
  }
});

module.exports = router;