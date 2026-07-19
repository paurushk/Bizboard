import { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import CircularProgress from '@mui/material/CircularProgress';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { universalSearch } from '@/api/resources';
import { t } from '@/i18n';
import type { SearchResult } from '@/types/domain';

export function UniversalSearch() {
  const navigate = useNavigate();
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

  const options = useMemo(() => query.data ?? [], [query.data]);

  return (
    <Autocomplete<SearchResult>
      sx={{ width: { xs: '100%', sm: 360 } }}
      options={options}
      loading={query.isFetching}
      filterOptions={(x) => x}
      getOptionLabel={(o) => o.title}
      inputValue={input}
      onInputChange={(_, value) => setInput(value)}
      onChange={(_, value) => {
        if (value) navigate(value.path);
      }}
      noOptionsText={debounced.length < 2 ? t('common.universalSearch') : t('common.noResults')}
      renderOption={(props, option) => (
        <li {...props} key={`${option.type}-${option.id}`}>
          <div>
            <Typography variant="body2" fontWeight={600}>
              {option.title}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {option.type}
              {option.subtitle ? ` · ${option.subtitle}` : ''}
            </Typography>
          </div>
        </li>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          placeholder={t('common.universalSearch')}
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
