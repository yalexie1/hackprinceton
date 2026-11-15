import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Node = {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName: string };
};

// Mark missing terms in the syntax tree; never turn document HTML into DOM.
function highlightBlanks() {
  return (tree: Node) => {
    function walk(node: Node) {
      if (!node.children || node.type === "code" || node.type === "inlineCode")
        return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text" || !child.value) {
          walk(child);
          return [child];
        }
        return child.value
          .split(/(\{\{[^}]+\}\}|\[\[BLANK:[^\]]+\]\])/g)
          .filter(Boolean)
          .map((value) =>
            value.startsWith("{{") || value.startsWith("[[BLANK:")
              ? {
                  type: "missingTerm",
                  data: { hName: value.includes("_box") ? "span" : "mark" },
                  children: [
                    {
                      type: "text",
                      value: value.includes("_box") ? "☐" : `${value
                        .replace(/^\{\{|\}\}$/g, "")
                        .replace(/^\[\[BLANK:\s*|\]\]$/g, "")
                        .split(",")[0]
                        .replaceAll("_", " ")
                        .trim()} — needs confirmation`,
                    },
                  ],
                }
              : { type: "text", value },
          );
      });
    }
    walk(tree);
  };
}

export default function DocumentText({
  text,
  variant = "document",
}: {
  text: string;
  variant?: "document" | "notice" | "report";
}) {
  return (
    <div
      className={
        variant === "notice"
          ? "document-disclaimer"
          : variant === "report"
            ? "audit-report"
            : "draft-text"
      }
    >
      <Markdown
        remarkPlugins={[remarkGfm, highlightBlanks]}
        skipHtml
        disallowedElements={["img", "input"]}
        components={{
          h1: ({ children }) => <h3>{children}</h3>,
          h2: ({ children }) => <h4>{children}</h4>,
          h3: ({ children }) => <h4>{children}</h4>,
          table: ({ children }) => (
            <div
              className="document-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Document table"
            >
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
