# Bước 1: build React bằng Vite. Bước 2: nginx phục vụ file tĩnh và proxy /api sang backend.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_URL rỗng => frontend gọi đường dẫn tương đối /api/v1/..., nginx chuyển tiếp sang backend
# (cùng origin, không cần CORS). Biến môi trường ưu tiên hơn file .env nên giá trị trong .env bị bỏ qua.
# VITE_GOONG_MAPTILES_KEY vẫn đọc từ .env (khóa tile bản đồ, vốn lộ ra trình duyệt).
ENV VITE_API_URL=
RUN npx vite build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
