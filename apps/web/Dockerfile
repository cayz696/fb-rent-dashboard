FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
ENV NODE_OPTIONS=--max-old-space-size=768
RUN npm run build
CMD ["npm", "run", "start"]
