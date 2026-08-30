import { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import CircularProgress from '@mui/material/CircularProgress';
import ListSubheader from '@mui/material/ListSubheader';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { universalSearch } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';
import { t } from '@/i18n';
import { isReallyReachable } from '@/navigation/menu';
import { buildHelpSearchHits } from '@/pages/help/searchHits';
import type { SearchResult } from '@/types/domain';

export function UniversalSearch() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const epoch = useFeatureFlagEpoch();
  const [input, setInput] = useState('');
  const [debounced, setDebounced] = useState('');

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(input.trim()), 250);
    return () => window.clearTimeout(id);
  }, [input]);

  const query = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => universalSearch(debounced),
    enabled: debounced.length >= 2,
  });

  const recordOptions = useMemo(
    () => (query.data ?? []).filter((hit) => isReallyReachable(user, hit.path)),
    [query.data, user],
  );

  const helpOptions = useMemo(() => {
    if (!isHelpV2Enabled() || debounced.length < 2) return [];
    return buildHelpSearchHits(debounced, recordOptions).filter((hit) =>
      isReallyReachable(user, hit.path),
    );
  }, [debounced, recordOptions, user, epoch]);

  const options = useMemo(() => [...recordOptions, ...helpOptions], [recordOptions, helpOptions]);

  return (
    <Autocomplete<SearchResult>
      sx={{ width: { xs: '100%', sm: 360 }, minWidth: 0, maxWidth: '100%' }}
      options={options}
      loading={query.isFetching}
      filterOptions={(x) => x}
      groupBy={(o) => (o.type === 'help' ? t('help.group') : '')}
      getOptionLabel={(o) => o.title}
      isOptionEqualToValue={(a, b) => a.type === b.type && String(a.id) === String(b.id)}
      inputValue={input}
      onInputChange={(_, value) => setInput(value)}
      onChange={(_, value) => {
        if (!value || !isReallyReachable(user, value.path)) return;
        navigate(value.path);
      }}
      noOptionsText={debounced.length < 2 ? t('common.search') : t('common.noResults')}
      renderGroup={(params) => (
        <li key={params.key}>
          {params.group ? (
            <ListSubheader component="div" disableSticky>
              {params.group}
            </ListSubheader>
          ) : null}
          <ul style={{ padding: 0, margin: 0 }}>{params.children}</ul>
        </li>
      )}
      renderOption={(props, option) => (
        <li {...props} key={`${option.type}-${option.id}`}>
          <div>
            <Typography variant="body2" fontWeight={600}>
              {option.title}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {option.type === 'help' ? option.subtitle : option.type}
              {option.type !== 'help' && option.subtitle ? ` · ${option.subtitle}` : ''}
            </Typography>
          </div>
        </li>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          placeholder={t('common.search')}
          inputProps={{
            ...params.inputProps,
            'aria-label': t('common.universalSearch'),
          }}
          sx={{
            '& .MuiInputBase-input': {
              fontSize: { xs: '0.875rem', sm: '0.875rem' },
            },
          }}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {query.isFetching ? <CircularProgress color="inherit" size={16} /> : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
    />
  );
}
