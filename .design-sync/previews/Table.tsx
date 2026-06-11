import * as React from "react";
import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "web";

const num: React.CSSProperties = { textAlign: "right" };

/** The cross-bank comparison table this design system was built around. */
export const BankComparison = () => (
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Bank</TableHead>
        <TableHead style={num}>Assets (₺ bn)</TableHead>
        <TableHead style={num}>NPL</TableHead>
        <TableHead style={num}>CAR</TableHead>
        <TableHead>Status</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      <TableRow>
        <TableCell>Ziraat Bankası</TableCell>
        <TableCell style={num}>5,418</TableCell>
        <TableCell style={num}>1.62%</TableCell>
        <TableCell style={num}>16.8%</TableCell>
        <TableCell><Badge variant="positive">Sound</Badge></TableCell>
      </TableRow>
      <TableRow>
        <TableCell>İş Bankası</TableCell>
        <TableCell style={num}>3,902</TableCell>
        <TableCell style={num}>2.18%</TableCell>
        <TableCell style={num}>17.1%</TableCell>
        <TableCell><Badge variant="positive">Sound</Badge></TableCell>
      </TableRow>
      <TableRow>
        <TableCell>Garanti BBVA</TableCell>
        <TableCell style={num}>3,655</TableCell>
        <TableCell style={num}>2.31%</TableCell>
        <TableCell style={num}>18.4%</TableCell>
        <TableCell><Badge variant="positive">Sound</Badge></TableCell>
      </TableRow>
      <TableRow>
        <TableCell>Yapı Kredi</TableCell>
        <TableCell style={num}>2,987</TableCell>
        <TableCell style={num}>2.74%</TableCell>
        <TableCell style={num}>15.9%</TableCell>
        <TableCell><Badge variant="warning">Watch</Badge></TableCell>
      </TableRow>
      <TableRow>
        <TableCell>Şekerbank</TableCell>
        <TableCell style={num}>214</TableCell>
        <TableCell style={num}>4.05%</TableCell>
        <TableCell style={num}>14.2%</TableCell>
        <TableCell><Badge variant="negative">Elevated NPL</Badge></TableCell>
      </TableRow>
    </TableBody>
  </Table>
);

/** Compact two-column metric list — the per-bank detail page pattern. */
export const MetricList = () => (
  <Table>
    <TableBody>
      <TableRow>
        <TableCell className="text-muted-foreground">Total deposits</TableCell>
        <TableCell style={num}>₺2,841 bn</TableCell>
      </TableRow>
      <TableRow>
        <TableCell className="text-muted-foreground">Loan / deposit ratio</TableCell>
        <TableCell style={num}>87.4%</TableCell>
      </TableRow>
      <TableRow>
        <TableCell className="text-muted-foreground">Stage 3 coverage</TableCell>
        <TableCell style={num}>74.9%</TableCell>
      </TableRow>
      <TableRow>
        <TableCell className="text-muted-foreground">Branches</TableCell>
        <TableCell style={num}>1,742</TableCell>
      </TableRow>
    </TableBody>
  </Table>
);
