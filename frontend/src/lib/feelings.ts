import { Coffee, Flame, Heart, Laugh, Sparkles, Zap, type LucideIcon } from 'lucide-react';
import { FEELINGS, type FeelingId, type Person } from '../api';

export const FEELING_ICONS: Record<FeelingId, LucideIcon> = {
  laugh: Laugh,
  edge: Zap,
  feels: Heart,
  mindblown: Sparkles,
  cozy: Coffee,
  hyped: Flame,
};

export const feelingOf = (p: Person) => FEELINGS.find((f) => f.id === p.feeling) ?? null;
