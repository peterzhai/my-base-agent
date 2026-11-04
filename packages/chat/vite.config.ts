import { defineConfig } from "vite";
export default defineConfig({
  build: {
    lib: {
      entry: "src/index.tsx",
      formats: ["es"],
      fileName: "index",
      cssFileName: "style",
    },
    rollupOptions: {
      external: ["react", "react-dom", "react/jsx-runtime", "antd"],
    },
    cssCodeSplit: false,
  },
});
