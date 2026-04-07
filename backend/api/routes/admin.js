const express = require('express');
const router = express.Router();
const multer = require('multer');
const { S3Client, PutObjectCommand } = require('@aws-sdk/client-s3');
const { v4: uuidv4 } = require('uuid');
const db = require('../database');


const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 500 * 1024 * 1024 } // 500 MB max
});

function requireAdmin(req, res, next) {
    const auth = req.headers['authorization'] || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : auth;
    const adminPassword = process.env.ADMIN_PASSWORD;

    if (!adminPassword) {
        return res.status(503).json({ error: 'Admin mode not configured on server' });
    }
    if (token !== adminPassword) {
        return res.status(401).json({ error: 'Invalid admin password' });
    }
    next();
}

// Build S3 client for Cloudflare R2
function getR2Client() {
    const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
    return new S3Client({
        region: 'auto',
        endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
        credentials: {
            accessKeyId: process.env.CLOUDFLARE_ACCESS_KEY_ID,
            secretAccessKey: process.env.CLOUDFLARE_SECRET_ACCESS_KEY,
        },
    });
}

async function uploadBufferToR2(buffer, key, contentType) {
    const s3 = getR2Client();
    await s3.send(new PutObjectCommand({
        Bucket: process.env.R2_BUCKET_NAME,
        Key: key,
        Body: buffer,
        ContentType: contentType,
    }));
    const domain = process.env.R2_PUBLIC_DOMAIN;
    return `https://${domain}/${key}`;
}

// POST /api/v1/admin/upload — upload a video to R2 and register it
router.post(
    '/upload',
    requireAdmin,
    upload.fields([
        { name: 'video', maxCount: 1 },
        { name: 'thumbnail', maxCount: 1 }
    ]),
    async (req, res) => {
        try {
            const videoFile = req.files?.['video']?.[0];
            if (!videoFile) {
                return res.status(400).json({ error: 'video file is required' });
            }

            const title = (req.body.title || '').trim() || null;
            const prompt = (req.body.prompt || title || 'Uploaded video').trim();
            const jobId = uuidv4();

            // upload video to R2
            const videoKey = `videos/${jobId}.mp4`;
            const videoUrl = await uploadBufferToR2(videoFile.buffer, videoKey, 'video/mp4');

            let thumbnailUrl = null;
            const thumbFile = req.files?.['thumbnail']?.[0];
            if (thumbFile) {
                const thumbKey = `thumbnails/${jobId}.jpg`;
                thumbnailUrl = await uploadBufferToR2(thumbFile.buffer, thumbKey, thumbFile.mimetype || 'image/jpeg');
            }

            const insertedId = await db.insertCompletedVideo(prompt, title, videoUrl, thumbnailUrl);
            res.json({ success: true, id: insertedId, videoUrl, thumbnailUrl });

        } catch (error) {
            console.error('Admin upload error:', error.message);
            res.status(500).json({ error: 'Upload failed: ' + error.message });
        }
    }
);

// DELETE /api/v1/admin/videos/:id
router.delete('/videos/:id', requireAdmin, async (req, res) => {
    try {
        await db.deleteVideoById(req.params.id);
        res.json({ success: true });
    } catch (error) {
        console.error('Admin delete error:', error.message);
        res.status(500).json({ error: 'Failed to delete video' });
    }
});

// PATCH /api/v1/admin/videos/:id  — rename
router.patch('/videos/:id', requireAdmin, async (req, res) => {
    try {
        const { title } = req.body;
        if (!title || !title.trim()) {
            return res.status(400).json({ error: 'title is required' });
        }
        await db.updateVideoTitle(req.params.id, title.trim());
        res.json({ success: true });
    } catch (error) {
        console.error('Admin rename error:', error.message);
        res.status(500).json({ error: 'Failed to rename video' });
    }
});

module.exports = router;
