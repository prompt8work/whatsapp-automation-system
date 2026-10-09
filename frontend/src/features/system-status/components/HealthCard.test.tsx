import { render, screen } from "@testing-library/react";

import { HealthCard } from "./HealthCard";

describe("HealthCard", () => {
  it("shows status and details", () => {
    render(
      <HealthCard health={{ status: "ok", environment: "local", version: "0.1.0" }} failed={false} />,
    );

    expect(screen.getByText("All systems operational")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
  });

  it("shows API unreachable when the request failed", () => {
    render(<HealthCard health={undefined} failed />);

    expect(screen.getByText("API unreachable")).toBeInTheDocument();
  });
});
