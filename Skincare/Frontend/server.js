const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const distPath = path.join(__dirname, 'dist/skin-care-app/browser');


console.log('Using distPath:', distPath);
console.log('index.html exists:', fs.existsSync(path.join(distPath, 'index.html')));

app.use((req, res, next) => {
  console.log(new Date().toISOString(), req.method, req.url);
  next();
});

// Serve static assets at expected mount
app.use('/skin-care-app/browser', express.static(distPath, {
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.js')) res.setHeader('Content-Type', 'application/javascript');
    if (filePath.endsWith('.css')) res.setHeader('Content-Type', 'text/css');
  }
}));

app.use(express.static(distPath));

// Root route
app.get('/', (req, res) => {
  const indexFile = path.join(distPath, 'index.html');
  if (fs.existsSync(indexFile)) return res.sendFile(indexFile);
  console.error('index.html not found at', indexFile);
  res.status(500).send('index.html not found on server');
});

// Safe SPA fallback
app.use((req, res) => {
  const indexFile = path.join(distPath, 'index.html');
  if (fs.existsSync(indexFile)) return res.sendFile(indexFile);
  console.error('index.html not found for fallback at', indexFile);
  res.status(404).send('Not Found');
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
