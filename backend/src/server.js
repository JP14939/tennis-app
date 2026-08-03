const express = require('express');
const cors = require('cors');
require('dotenv').config();

const analyseRouter = require('./routes/analyse');
const authRouter = require('./routes/auth');

const app = express();
app.use(cors());
app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'OK', message: 'Server is running' });
});

app.use('/api', analyseRouter);
app.use('/api', authRouter);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
