from src import __version__


def version(args, parser):
    if args.root:
        print(args.root_path)
    else:
        print(__version__)


def make_parser(parser):
    parser.add_argument(
        "-r",
        "--root",
        action="store_true",
        help="Display root directory",
    )

    parser.set_defaults(function=version)
    return parser
