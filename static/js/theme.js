// Light/dark theme toggle. CSS handles the actual colors via [data-theme="light"] in
// styles.css; this module just flips the attribute and pushes the refreshed tokens into
// the chart, which Lightweight Charts doesn't otherwise know to re-read.
import { applyThemeToChart } from './chart.js';
import { refreshColors } from './state.js';

export function applyTheme(mode) {
  document.documentElement.dataset.theme = mode;
  refreshColors();
  applyThemeToChart();
}
