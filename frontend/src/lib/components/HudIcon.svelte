<script lang="ts">
  export type HudIconName =
    | "add"
    | "attach"
    | "assistants"
    | "brain"
    | "team"
    | "chat"
    | "check"
    | "chevron"
    | "destroy"
    | "key"
    | "retry"
    | "send"
    | "session"
    | "shield"
    | "stop"
    | "uninstall"
    | "user";

  let { name, size = 20 }: { name: HudIconName; size?: number } = $props();
</script>

<svg
  aria-hidden="true"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.6"
  stroke-linecap="square"
  stroke-linejoin="miter">
  {#if name === "team"}
    <path d="m12 2.8 7.8 4.5v9.4L12 21.2l-7.8-4.5V7.3L12 2.8Z" />
    <path d="M8.2 9.2 12 7l3.8 2.2v5.6L12 17l-3.8-2.2V9.2Z" />
    <path d="M12 2.8V7m7.8.3-4 1.9m4 7.5-4-1.9M12 21.2V17m-7.8-.3 4-1.9m-4-7.5 4 1.9" />
  {:else if name === "assistants"}
    <path d="M6 8.5h12v9H6zM9 8.5V6h6v2.5M9 12h.01M15 12h.01M9 15h6" />
    <path d="M3.5 11v4M20.5 11v4M12 3v3" />
  {:else if name === "chat"}
    <path d="M4 4.5h16v11H9l-5 4v-15Z" />
    <path d="M8 9h8M8 12h5" />
  {:else if name === "destroy"}
    <path d="M7 7h10l-.7 13H7.7L7 7ZM5 7h14M9 7V4h6v3M10 10v6M14 10v6" />
    <path d="m4 3 16 18" />
  {:else if name === "uninstall"}
    <path d="M5 4h9v16H5zM14 9h5v6h-5M10 12h9M16.5 9.5 19 12l-2.5 2.5" />
  {:else if name === "add"}
    <path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M12 7v10M7 12h10" />
  {:else if name === "attach"}
    <path d="m8 12.5 6.7-6.7a3.2 3.2 0 0 1 4.5 4.5l-8.5 8.5a5 5 0 0 1-7.1-7.1l8-8" />
  {:else if name === "chevron"}
    <path d="m8 10 4 4 4-4" />
  {:else if name === "brain"}
    <path d="M9.2 4.2A3 3 0 0 0 4.8 7a3 3 0 0 0-1.1 5 3.2 3.2 0 0 0 2.5 5.2A3 3 0 0 0 12 18V6a3 3 0 0 0-2.8-1.8Z" />
    <path d="M14.8 4.2A3 3 0 0 1 19.2 7a3 3 0 0 1 1.1 5 3.2 3.2 0 0 1-2.5 5.2A3 3 0 0 1 12 18M8 9h4M12 13h4M7 15h2M15 7h2" />
  {:else if name === "key"}
    <circle cx="8" cy="12" r="4" />
    <path d="M12 12h8M17 12v3M20 12v2" />
  {:else if name === "shield"}
    <path d="M12 3 19 6v5.5c0 4.4-2.8 7.6-7 9.5-4.2-1.9-7-5.1-7-9.5V6l7-3Z" />
    <path d="m8.5 12 2.2 2.2 4.8-5" />
  {:else if name === "user"}
    <circle cx="12" cy="8" r="3.2" />
    <path d="M5.5 20v-2.2c0-3 2.9-5.3 6.5-5.3s6.5 2.3 6.5 5.3V20" />
  {:else if name === "session"}
    <path d="M4 5h10v14H4zM14 8h6v8h-6M9 12h11M17 9l3 3-3 3" />
  {:else if name === "check"}
    <path d="m4.5 12 4.7 4.7L19.5 6.5" />
  {:else if name === "retry"}
    <path d="M19 8V4l-2 2a8 8 0 1 0 2.2 8" />
  {:else if name === "send"}
    <path d="m3.5 4 17 8-17 8 3-8-3-8Z" />
    <path d="M6.5 12h9" />
  {:else if name === "stop"}
    <path d="M6 6h12v12H6z" />
  {/if}
</svg>

<style>
  svg { display: block; flex: none; overflow: visible; }
  path, circle { vector-effect: non-scaling-stroke; }
</style>
