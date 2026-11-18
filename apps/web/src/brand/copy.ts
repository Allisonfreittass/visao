// Words of the brand that are not data: who it greets and how. One owner, one assistant.
import { greeting } from "../components/Intro";

/** The owner's first name, for the greeting on Início (the API keeps no name, only an email). */
export const OWNER_NAME = "Allison";

export const BRAND_NAME = "V.I.S.A.O.";

/** "Boa noite, Allison." by the hour on this device. */
export function homeGreeting(now = new Date(), name = OWNER_NAME): string {
  return `${greeting(now.getHours())}, ${name}.`;
}

/** Suggestions above the message box on Início: tapping one writes it in the box. */
export const HOME_SUGGESTIONS: { label: string; draft: string }[] = [
  { label: "Resumo do meu dia", draft: "Me dá um resumo do meu dia" },
  { label: "Acompanhar um preço", draft: "Quero acompanhar " },
  { label: "Pedir algo ao Mac", draft: "/mac " },
];
