const express = require('express');
const app = express();

app.use(express.json());

app.get('/api/products', (req, res) => {
    res.json([]);
});

app.post('/api/products', (req, res) => {
    res.status(201).json({ id: 1, ...req.body });
});

app.get('/api/products/:id', (req, res) => {
    res.json({ id: req.params.id });
});

app.delete('/api/products/:id', (req, res) => {
    res.status(204).send();
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
