import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import { Link as RouterLink } from 'react-router-dom';
import type { AgentEvidence } from '@/api/agents';
import { safeAppPath } from '@/utils/safeUrl';

/** Every claim in a draft cites something the user can open. */
export function EvidenceList({ evidence }: { evidence: AgentEvidence[] }) {
  return (
    <List dense disablePadding>
      {evidence.map((item) => {
        const href = item.href ? safeAppPath(item.href) : null;
        const key = `${item.type}:${item.id}`;
        return (
          <ListItem key={key} disableGutters>
            <ListItemText
              primary={
                href ? (
                  <Link component={RouterLink} to={href} underline="hover">
                    {item.label}
                  </Link>
                ) : (
                  item.label
                )
              }
            />
          </ListItem>
        );
      })}
    </List>
  );
}
