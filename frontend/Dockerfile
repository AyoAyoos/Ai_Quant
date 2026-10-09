# Build the static bundle, then serve it with nginx. The browser talks to
# the backend directly (default http://localhost:8000, override at build
# time with --build-arg VITE_API_BASE=...), so no proxy config is needed.
# Supabase auth is also baked in at build time (Vite inlines VITE_* vars):
# without these args the bundle falls back to prototype auth and every
# authenticated backend call answers 401.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE=http://localhost:8000
ARG VITE_API_BASE_URL=
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_ANON_KEY=
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
RUN npm run build

FROM nginx:1.27-alpine
# Default nginx.conf has no SPA fallback, so /chat and /strategies/:id would 404
# on a direct load or refresh. Copy ours over it.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
