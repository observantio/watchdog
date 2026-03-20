FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_OTLP_GATEWAY_HOST
ENV VITE_OTLP_GATEWAY_HOST=$VITE_OTLP_GATEWAY_HOST
COPY package.json package-lock.json* ./
RUN npm ci --include=optional
COPY . .
RUN NODE_ENV=production npm run build

FROM nginx:1.27-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]