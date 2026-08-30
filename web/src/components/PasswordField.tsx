import { forwardRef, useState } from 'react';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import TextField, { type TextFieldProps } from '@mui/material/TextField';
import useForkRef from '@mui/utils/useForkRef';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';

/** Password input with an accessible show/hide toggle (E2E3-004). */
export const PasswordField = forwardRef<HTMLInputElement, TextFieldProps>(
  function PasswordField({ InputProps, inputRef, ...props }, ref) {
    const [visible, setVisible] = useState(false);
    const handleInputRef = useForkRef(ref, inputRef);
    return (
      <TextField
        {...props}
        type={visible ? 'text' : 'password'}
        inputRef={handleInputRef}
        InputProps={{
          ...InputProps,
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                type="button"
                aria-label={visible ? 'Hide password' : 'Show password'}
                onClick={() => setVisible((v) => !v)}
                onMouseDown={(event) => event.preventDefault()}
                edge="end"
              >
                {visible ? <VisibilityOff /> : <Visibility />}
              </IconButton>
              {InputProps?.endAdornment}
            </InputAdornment>
          ),
        }}
      />
    );
  },
);
