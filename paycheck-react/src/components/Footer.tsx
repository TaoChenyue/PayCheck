// paycheck-react/src/components/Footer.tsx

interface FooterProps {
  generatedAt: string;
}

export default function Footer({ generatedAt }: FooterProps) {
  return (
    <footer style={{ textAlign: "center", padding: 20, color: "#aaa", fontSize: 13 }}>
      <p>PayCheck · 总账户（微信 + 支付宝 + 银行） · {generatedAt}</p>
    </footer>
  );
}
