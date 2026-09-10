import type { SceneOptions } from './types';

type Tool = {
  name: string;
  title: string;
  description: string;
  inputSchema: object;
  annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
  execute: (input: unknown) => unknown;
};
type ModelContext = {
  registerTool: (
    tool: Tool,
    options: { signal: AbortSignal },
  ) => void | Promise<void>;
};
type Actions = {
  read: () => {
    ready: boolean;
    options: SceneOptions;
    landmarks: { id: string; name: string }[];
  };
  focus: (id: string | null) => void;
  configure: (patch: {
    hour?: number;
    topDown?: boolean;
    layers?: Record<string, boolean>;
  }) => void;
};
const nextPaint = () =>
  new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );

/** Feature-detected page tools; all mutations use the same React actions as the UI. */
export function registerAtlasTools(actions: Actions): () => void {
  const context = (document as Document & { modelContext?: ModelContext })
    .modelContext;
  if (!context?.registerTool) return () => {};
  const lifecycle = new AbortController();
  const layerKeys = ['buildings', 'vegetation', 'roads', 'railways', 'water', 'labels'];
  const object = (input: unknown): Record<string, unknown> => {
    if (!input || typeof input !== 'object' || Array.isArray(input))
      throw new Error('Expected an object');
    return input as Record<string, unknown>;
  };
  const tools: Tool[] = [
    {
      name: 'read_nanning_atlas',
      title: '读取南宁沙盘',
      description: 'Read the loaded landmarks and current map settings.',
      inputSchema: {
        type: 'object',
        properties: {},
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true, untrustedContentHint: false },
      execute: () => actions.read(),
    },
    {
      name: 'focus_nanning_landmark',
      title: '前往南宁地标',
      description:
        'Move the visible camera to a listed landmark, or overview for the whole city.',
      inputSchema: {
        type: 'object',
        properties: { id: { type: 'string' } },
        required: ['id'],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute: async (input) => {
        const value = object(input);
        const state = actions.read();
        if (!state.ready) throw new Error('The city is still loading');
        if (
          Object.keys(value).some((k) => k !== 'id') ||
          typeof value.id !== 'string' ||
          (value.id !== 'overview' &&
            !state.landmarks.some((p) => p.id === value.id))
        )
          throw new Error('Unknown landmark id; read the atlas first');
        actions.focus(value.id === 'overview' ? null : value.id);
        await nextPaint();
        return {
          focused: value.id,
          camera: 'moving',
          options: actions.read().options,
        };
      },
    },
    {
      name: 'configure_nanning_scene',
      title: '调整南宁场景',
      description:
        'Set simulated time, overhead view, or multiple visible layers in one action.',
      inputSchema: {
        type: 'object',
        properties: {
          hour: { type: 'number', minimum: 6, maximum: 22 },
          topDown: { type: 'boolean' },
          layers: {
            type: 'object',
            properties: Object.fromEntries(
              layerKeys.map((key) => [key, { type: 'boolean' }]),
            ),
            additionalProperties: false,
          },
        },
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute: async (input) => {
        const value = object(input);
        if (!actions.read().ready) throw new Error('The city is still loading');
        if (
          Object.keys(value).some(
            (key) => !['hour', 'topDown', 'layers'].includes(key),
          )
        )
          throw new Error('Unknown scene option');
        if (
          value.hour !== undefined &&
          (typeof value.hour !== 'number' ||
            !Number.isFinite(value.hour) ||
            value.hour < 6 ||
            value.hour > 22 ||
            (value.hour * 2) % 1 !== 0)
        )
          throw new Error('hour must be 6–22 in half-hour increments');
        if (value.topDown !== undefined && typeof value.topDown !== 'boolean')
          throw new Error('topDown must be boolean');
        if (value.layers !== undefined) {
          const layers = object(value.layers);
          if (
            Object.entries(layers).some(
              ([key, v]) => !layerKeys.includes(key) || typeof v !== 'boolean',
            )
          )
            throw new Error('Invalid layer setting');
        }
        actions.configure(value as Parameters<Actions['configure']>[0]);
        await nextPaint();
        return actions.read().options;
      },
    },
  ];
  for (const tool of tools) {
    try {
      void Promise.resolve(
        context.registerTool(tool, { signal: lifecycle.signal }),
      ).catch(() => {});
    } catch {
      /* The map remains available if the experimental registry rejects a tool. */
    }
  }
  return () => lifecycle.abort();
}
