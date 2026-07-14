import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

// Static public product and driver documentation; authenticated Capsule operations stay under /api.
export default {
  preprocess: vitePreprocess(),
  kit: { adapter: adapter({ strict: false }) },
};
