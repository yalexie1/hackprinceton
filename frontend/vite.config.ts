import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  return {
    plugins: [react()],
    // Only the browser-scoped Showcase key is exposed; API credentials stay server-side.
    define: {
      __MATTERPORT_SDK_KEY__: JSON.stringify(
        env.MATTERPORT_SDK_KEY || env.VITE_MATTERPORT_SDK_KEY || "",
      ),
    },
    envDir: root,
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("preload-helper") || id.includes("commonjsHelpers")) return "vendor";
            if (id.includes("/node_modules/") && /\/(jspdf|fflate|fast-png|iobuffer|pako|canvg|core-js|dompurify|html2canvas|rgbcolor|stackblur-canvas|svg-pathdata|raf|text-segmentation|utrie|css-line-break|base64-arraybuffer)\//.test(id)) return "pdf-export";
            if (id.includes("/node_modules/three/")) return "architecture";
            if (id.includes("/node_modules/")) return "vendor";
            if (id.includes("/fixtures/") || id.includes("/specs/examples/"))
              return "examples";
          },
        },
      },
    },
    server: {
      proxy: {
        "/api": {
          target: env.FRONTEND_API_PROXY || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
