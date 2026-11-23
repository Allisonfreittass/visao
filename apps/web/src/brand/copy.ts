// Words of the brand that are not data: who it greets and how. One owner, one assistant.
import { greeting } from "../components/Intro";

/** The owner's first name, for the greeting on Início (the API keeps no name, only an email). */
export const OWNER_NAME = "Allison";

export const BRAND_NAME = "V.I.S.A.O.";

/** "Boa noite, Allison." by the hour on this device. */
export function homeGreeting(now = new Date(), name = OWNER_NAME): string {
  return `${greeting(now.getHours())}, ${name}.`;
}
