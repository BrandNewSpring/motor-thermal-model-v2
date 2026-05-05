declare module "plotly.js-dist-min" {
  import Plotly from "plotly.js";
  export default Plotly;
}

declare module "react-plotly.js/factory" {
  import type { ComponentType } from "react";
  import type Plotly from "plotly.js";
  interface PlotParams {
    data: Plotly.Data[];
    layout?: Partial<Plotly.Layout>;
    config?: Partial<Plotly.Config>;
    [key: string]: unknown;
  }
  const createPlotlyComponent: (plotly: typeof Plotly) => ComponentType<PlotParams>;
  export default createPlotlyComponent;
}
