# Open AML Compliance Sidecar demo frontend (Vite build, served with vite preview)
FROM node:22-alpine

WORKDIR /app

# Install deps first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build with the API base URL baked in (Vite inlines import.meta.env at build).
COPY . .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

EXPOSE 5173
# vite preview serves the production build and handles SPA (deep-link) fallback.
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
