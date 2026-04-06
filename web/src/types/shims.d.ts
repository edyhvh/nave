declare global {
  namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}

declare module "react" {
  export type PropsWithChildren<P = {}> = P & {
    children?: React.ReactNode | undefined;
  };
  export function useState<T>(initial: T): [T, React.SetStateAction<T>];
  export function useEffect(
    callback: () => void | (() => void),
    deps?: any[],
  ): void;
  export function useCallback<T>(callback: T, deps: any[]): T;
  export function useRef<T>(initial: T): { current: T };
  export interface ReactNode {}
  export type SetStateAction<S> = S | ((prevState: S) => S);
  export interface Dispatch<A> {
    (value: A): void;
  }
}

declare module "react/jsx-runtime" {
  export namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}

declare module "react-dom" {}

declare module "@/lib/*" {
  const content: any;
  export default content;
  export const apiClient: any;
  export class APIClientError extends Error {}
}

declare module "@/types/*" {
  const content: any;
  export default content;
  export interface IndicatorResponse {}
  export interface APIError {}
  export interface UseIndicatorResult {}
  export interface UseIndicatorsResult {}
}

declare module "@/hooks/*" {
  const content: any;
  export default content;
}

declare module "@/components/*" {
  const content: any;
  export default content;
}
