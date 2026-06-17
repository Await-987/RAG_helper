import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';

interface ReasoningBlockProps {
  content: string;
}

export function ReasoningBlock({ content }: ReasoningBlockProps) {
  return (
    <Accordion type="single" collapsible defaultValue="reasoning" className="border-none">
      <AccordionItem value="reasoning" className="border-none">
        <AccordionTrigger className="py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:no-underline">
          思考过程
        </AccordionTrigger>
        <AccordionContent className="text-sm text-zinc-400 leading-relaxed">
          <div className="rounded-xl bg-zinc-800/40 border border-white/[0.04] p-3">
            {content}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}