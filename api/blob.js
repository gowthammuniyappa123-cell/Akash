const { handleUpload } = require("@vercel/blob/client");

const ALLOWED_CONTENT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "video/mp4",
  "video/webm",
  "video/ogg",
  "video/quicktime",
  "video/x-matroska",
  "video/x-msvideo",
];

const MAX_FILE_SIZE_BYTES = 250 * 1024 * 1024;

function parseJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";

    req.on("data", (chunk) => {
      body += chunk;
    });

    req.on("end", () => {
      if (!body) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(new Error("Invalid JSON body"));
      }
    });

    req.on("error", () => reject(new Error("Request body read failed")));
  });
}

module.exports = async function handler(req, res) {
  if (req.method === "OPTIONS") {
    res.status(200).end();
    return;
  }

  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  let body;

  try {
    body = await parseJsonBody(req);
  } catch (error) {
    res.status(400).json({ error: error.message || "Invalid upload request" });
    return;
  }

  if (body.action === "delete") {
    const { del } = await import("@vercel/blob");
    const url = body.url;

    if (!url) {
      res.status(400).json({ error: "Missing blob URL" });
      return;
    }

    try {
      await del(url);
      res.status(200).json({ success: true });
    } catch (error) {
      res.status(500).json({ error: error.message || "Failed to delete blob" });
    }

    return;
  }

  const request = new Request(
    `https://${req.headers.host || "localhost"}${req.url}`,
    {
      method: req.method,
      headers: req.headers,
      body: JSON.stringify(body),
    },
  );

  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname, clientPayload) => {
        const payload = JSON.parse(clientPayload || "{}") || {};

        if (!payload.password || payload.password !== process.env.UPLOAD_PASSWORD) {
          throw new Error("Incorrect password");
        }

        if (!payload.description || !String(payload.description).trim()) {
          throw new Error("Description is required");
        }

        return {
          allowedContentTypes: ALLOWED_CONTENT_TYPES,
          maximumSizeInBytes: MAX_FILE_SIZE_BYTES,
          addRandomSuffix: true,
          tokenPayload: JSON.stringify({
            password: payload.password,
            description: payload.description,
          }),
        };
      },
      onUploadCompleted: async ({ blob, tokenPayload }) => {
        if (!blob || !blob.url) {
          throw new Error("Upload completed without a blob URL");
        }
      },
    });

    res.status(200).json(jsonResponse);
  } catch (error) {
    res.status(400).json({
      error: error.message || "Upload failed. Please try again.",
    });
  }
};
