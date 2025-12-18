# --- Build Stage ---
# Use a Node.js version that is compatible with Nuxt 4
FROM node:18-slim AS build-stage

# Build-time args from docker-compose.prod.yml
ARG APP_NAME
ARG PROJECT_NAME

# Expose to Nuxt build environment
ENV APP_NAME=${APP_NAME}
ENV PROJECT_NAME=${PROJECT_NAME}

# Set working directory
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy package.json and lockfile
COPY package.json pnpm-lock.yaml ./

# Install all dependencies (including devDependencies needed for build)
RUN pnpm install

# Copy the rest of the frontend application code
COPY . .

# Build the application for production
RUN pnpm build

# --- Final Stage ---
# Use a lightweight Node.js image for the final production image
FROM node:18-alpine AS final-stage

# Set working directory
WORKDIR /app

# Copy the built output from the build stage
COPY --from=build-stage /app/.output ./.output

# Nuxt 4 starts its own server, so we only need to copy the output.
# We don't need the full package.json or node_modules in the final image.

# Expose the port Nuxt 4 runs on (default is 3000)
EXPOSE 3000

# Command to start the Nuxt 4 server in production mode
CMD ["node", ".output/server/index.mjs"] 
