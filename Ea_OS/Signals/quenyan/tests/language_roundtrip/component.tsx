import React from 'react';

type ButtonProps = {
  label: string;
  onClick?: () => void;
};

export const FancyButton: React.FC<ButtonProps> = ({ label, onClick }) => {
  return (
    <button className="fancy" onClick={onClick}>
      {label.toUpperCase()}
    </button>
  );
};
